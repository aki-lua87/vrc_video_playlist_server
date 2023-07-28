import os
import json
import boto3
from datetime import datetime, timedelta
import random
import ddbutils
import ytutils

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['VRC_VIDEO_TABLE'])

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
    if queryStringParameters is not None:
        register_id = queryStringParameters.get('id', '')
        # register_idにrandomが含まれる文字列の場合
        if 'random' in register_id:
            is_random = True

    print('register_id:', register_id)

    count = 0

    # チャンネルが存在するか確認
    record = ddbutils.is_exist_continuous_playlist_id(playlist_id, register_id)

    print('受信ip_address:', ip_address)
    # チャンネルが存在しない場合は新規登録し0番を返却
    if record is None:
        try:
            print('初回登録')
            # Youtubeから取得
            video_list = ytutils.ytapi_search_playlist(playlist_id)
        except Exception as e:
            print('ytapi_search_playlist Error: ', e)
            return return404()
        print('video_list', video_list)
        if len(video_list) == 0:
            return return404()
        urls = video_list['videos']['urls']
        titles = video_list['videos']['titles']
        # url = urls[0]
        # title = titles[0]
        # DynamoDBに登録
        ddbutils.regist_continuous_playlist_video_list(video_list, ip_address, get_ttl_hours(12), register_id)
        if is_random:
            count = random.randint(0, len(urls)-1)
            print('count(random regist):', count)
            ddbutils.update_randcount_continuous_playlist_id(playlist_id, register_id, count)
    else:
        # IPを確認
        isPublishedUser = False
        regist_ip_address = record.get('ip_address', None)
        if ip_address == regist_ip_address:
            isPublishedUser = True
        print('登録ip_address:', regist_ip_address)
        print('isPublishedUser:', isPublishedUser)
        urls = record.get('urls')
        titles = record.get('titles')

        # StringLoader
        if PC_AE != ae:
            print('StringLoaderでの返却')
            if is_random:
                count = record.get('random_count')
            else:
                count = record.get('_count')
            title = titles[int(count)]
            if isPublishedUser:
                # 登録者はタイトルを返さない(タイミングがズレます、マジで) ランダムなければ+1と踏めたけどランダムのせいで無理 間違えたの返すくらいなら無を返します
                title = ''
            return {
                'headers': {
                    "Content-type": "text/html; charset=utf-8",
                    "Access-Control-Allow-Origin": "*",
                },
                'statusCode': 200,
                'body': '{"title":"'+title+'"}',
            }

        # 登録者はカウントアップ
        if isPublishedUser:
            count = ddbutils.countup_continuous_playlist_id(playlist_id, register_id)
            count = int(count)
            print(f'count(up): {count}')
            # 配列越えの時に0に戻す
            if count >= len(urls):
                count = 0
                ddbutils.reset_continuous_playlist_id(playlist_id, register_id)
                print('count(reset): 0')
            if is_random:
                count = random.randint(0, len(urls)-1)
                print('count(random):', count)
                ddbutils.update_randcount_continuous_playlist_id(playlist_id, register_id, count)
        else:
            if is_random:
                count = record.get('random_count')
                print('count(random そのまま):', count)
            else:
                count = record.get('_count')
                print(f'count(そのまま): {count}')
        print('count:', int(count))

    url = urls[count]
    title = titles[count]
    print('返却URL')
    print(url, title)
    if QUEST_UA in ua:
        # Quest処理
        print('Quest Request')
        url = resolvURL(url)
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


def resolvURL(url):
    quest_url = ddbutils.getQuestURL(url)
    if quest_url is not None:
        print('use DynamoDB record')
        return quest_url
    b = ytutils.exec_ytdlp_cmd(url)
    quest_url = b.decode()
    print(quest_url)
    ttl = get_ttl_minute(15)
    ddbutils.registQuestURL(url, quest_url, ttl)
    return quest_url


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
