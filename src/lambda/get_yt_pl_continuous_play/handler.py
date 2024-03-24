import os
import json
import boto3
from datetime import datetime, timedelta
import random
import ddbutils
import time

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['VRC_VIDEO_TABLE'])

regist_lambda_name = os.environ['REGIST_LAMBDA_NAME']

PC_UA1 = 'Mozilla/5.0'
PC_UA2 = 'NSPlayer'
QUEST_UA = 'stagefright'
PC_AE = 'identity'  # 'Accept-Encoding': '*'

cf_domain = os.environ['CF_DOMAIN']
URL_404 = f'{cf_domain}/nf.mp4'


def main(event, context):
    print('event:', event)
    playlist_id = event['pathParameters'].get('playlist_id')
    playlist_id = playlist_id.strip()
    httpMethod = event.get('httpMethod')
    ua = event.get('headers').get('User-Agent', '')
    ae = event.get('headers').get('Accept-Encoding', '')
    ip_address = event.get('headers').get('X-Forwarded-For', 'Anonymous')
    ip_address = ip_address.split(',')[0]
    print('playlist_id:', playlist_id)
    print('httpMethod:', httpMethod)
    print('User-Agent:', ua)
    print('Accept-Encoding:', ae)
    if playlist_id is None:
        return {
            'headers': {
                "Access-Control-Allow-Origin": "*"
            },
            'statusCode': 400,
            'body': json.dumps(
                {
                    'result': 'NG',
                    'error': 'bad request'
                }
            )
        }
    queryStringParameters = event.get('queryStringParameters')
    register_id = ''
    is_random = False
    is_first = False
    if queryStringParameters is not None:
        register_id = queryStringParameters.get('id', '')
        # register_idにrandomが含まれる文字列の場合
        if 'random' in register_id:
            is_random = True

    print('register_id:', register_id)
    print('受信ip_address:', ip_address)

    count = 0

    # StringLoader対応
    if PC_AE != ae:
        count = 0
        time.sleep(1.5)  # YTTL 共通 1.5
        record = ddbutils.is_exist_continuous_playlist_id(playlist_id, register_id)
        if record is None:
            time.sleep(1.5)  # YTTL 予備 1.5
            record = ddbutils.is_exist_continuous_playlist_id(playlist_id, register_id)
            if record is None:
                print('Record None')
                return return404()
            if is_random:
                count = record.get('random_count')
            else:
                count = record.get('_count')
        else:
            isPublishedUser = False
            regist_ip_address = record.get('ip_address', None)
            if ip_address == regist_ip_address:
                isPublishedUser = True
            if not isPublishedUser:
                print('DEBUG 1秒待機前', record)
                time.sleep(1)  # YTTL 非ホスト 1
                record = ddbutils.is_exist_continuous_playlist_id(playlist_id, register_id)
                print('DEBUG 1秒待機後', record)
            if is_random:
                count = record.get('random_count')
            else:
                count = record.get('_count')
        titles = record.get('titles')
        title = titles[int(count)]
        print('StringLoaderでの返却', title, ip_address)
        return {
            'headers': {
                "Content-type": "text/html; charset=utf-8",
                "Access-Control-Allow-Origin": "*",
            },
            'statusCode': 200,
            'body': '{"title":"'+title+'"}',
        }

    # チャンネルが存在するか確認
    record = ddbutils.is_exist_continuous_playlist_id(playlist_id, register_id)

    # チャンネルが存在しない場合は新規登録し0番を返却
    if record is None:
        print('初回登録')
        try:
            is_first = True
            payload = {"register_id": register_id, "playlist_id": playlist_id, "ip_address": ip_address}
            # Lambda関数を呼び出し登録する。同期。
            _ = boto3.client('lambda').invoke(
                FunctionName=regist_lambda_name,
                InvocationType='RequestResponse',  # 同期
                Payload=json.dumps(payload),
            )
            record = ddbutils.is_exist_continuous_playlist_id(playlist_id, register_id)
            if record is None:
                print('Error Record None[初回登録Lambdaエラー]')
                return return404()
        except Exception as e:
            print('regist Error: ', e)
            return return404()

    # IPを確認
    isPublishedUser = False
    regist_ip_address = record.get('ip_address', None)
    if ip_address == regist_ip_address:
        isPublishedUser = True
    urls = record.get('urls')
    titles = record.get('titles')

    # count値を取得
    if isPublishedUser:
        if is_random:
            count = random.randint(0, len(urls)-1)
            print('count(random):', count)
            ddbutils.update_randcount_continuous_playlist_id(playlist_id, register_id, count)
        else:
            if is_first:
                count = 0
                print('count(first regist):', count)
            else:
                count = ddbutils.countup_continuous_playlist_id(playlist_id, register_id)
                count = int(count)
                print(f'count(up): {count}')
                # 配列越えの時に0に戻す
                if count >= len(urls):
                    count = 0
                    ddbutils.reset_continuous_playlist_id(playlist_id, register_id)
                    print('count(reset): 0')
    else:
        time.sleep(3)  # メイン処理 非ホスト 2
        # 非ホストの場合待機後再度取得
        record = ddbutils.is_exist_continuous_playlist_id(playlist_id, register_id)
        if is_random:
            count = record.get('random_count')
            print('count(random そのまま):', count)
        else:
            count = record.get('_count')
            print(f'count(そのまま): {count}')
        count = int(count)
    print('isPublishedUser:', isPublishedUser)  # 登録者かどうか(scopeはここ)

    url = urls[count]
    title = titles[count]
    print('通常アクセス', title, ip_address)
    if QUEST_UA in ua:
        # Quest処理
        print('Quest Request')
        # url = resolvURL(url)
    elif ae == PC_AE:
        # PC処理
        # print('PC Request::: 特別対応実施中')
        print('PC Request')
        # url = resolvURL(url)
    else:
        # Other Youtubeにリダイレクト
        print('Not VRC Request')
    return {
        'headers': {
            "Content-type": "text/html; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
            "location": url
        },
        'statusCode': 302,
        'body': "",
    }


def get_ttl_minute(minute):
    start = datetime.now()
    expiration_date = start + timedelta(minutes=minute)
    return round(expiration_date.timestamp())


def get_ttl_hours(hour):
    start = datetime.now()
    expiration_date = start + timedelta(hours=hour)
    return round(expiration_date.timestamp())


def return404():
    return {
        'headers': {
            "Content-type": "text/html; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
            "location": URL_404
        },
        'statusCode': 302,
        'body': "",
    }
