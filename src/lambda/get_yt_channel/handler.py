import os
import urllib.request
import json
import boto3
from datetime import datetime, timedelta

import ddbutils
import ytutils

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['VRC_VIDEO_TABLE'])

PC_UA1 = 'Mozilla/5.0'
PC_UA2 = 'NSPlayer'
QUEST_UA = 'stagefright'
PC_AE = 'identity'  # 'Accept-Encoding': 'identity'

cf_domain = os.environ['CF_DOMAIN']
URL_404 = f'{cf_domain}/nf.mp4'

QUEST_MODE = os.environ.get('QUEST_MODE', 'true')


def main(event, context):
    print('event:', event)
    channel_id = event['pathParameters'].get('channel_id')
    channel_id = channel_id.strip()
    queryStringParameters = event.get('queryStringParameters')
    httpMethod = event.get('httpMethod')
    ua = event.get('headers').get('User-Agent', '')
    ae = event.get('headers').get('Accept-Encoding', '')
    print('channel_id:', channel_id)
    print('httpMethod:', httpMethod)
    print('User-Agent:', ua)
    print('Accept-Encoding:', ae)
    if channel_id is None or queryStringParameters is None:
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
    before = queryStringParameters.get('n', 0)
    b_int = int(before)
    url, title = getVideoURL(channel_id, b_int)
    if QUEST_UA in ua:
        # Quest処理
        print('Quest Request Mode')
        url = resolvURL(url)
    elif ae == PC_AE:
        # PC処理
        # print('PC Request::: 特別対応実施中')
        print('PC Request Mode')
        if QUEST_MODE == 'true':
            url = resolvURL(url)
            print('QUEST MODE:', url)
    else:
        # Other Youtubeにリダイレクト
        print('StringLoader Mode')

        # YTTL JSONを返却
        return {
            'headers': {
                "Content-type": "text/html; charset=utf-8",
                "Access-Control-Allow-Origin": "*",
            },
            'statusCode': 200,
            'body': '{"title":"'+title+'"}',
        }
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
    print('resolvURL:', url)
    quest_url = ddbutils.getQuestURL(url)
    if quest_url is not None:
        print('use DynamoDB record:' + quest_url)
        return quest_url
    b = ytutils.exec_ytdlp_cmd(url)
    quest_url = b.decode()
    print(quest_url)
    ttl = get_ttl()
    ddbutils.registQuestURL(url, quest_url, ttl)
    return quest_url


def getVideoURL(channel_id, n):
    is_update = False
    # Videoのlistを取得
    v_list = ddbutils.getVideoList(channel_id)
    if v_list is None:
        is_update = True
    else:
        # 更新有無の確認
        latestDateStr = v_list.get('latest_update', 'NoData')
        print('latestDateStr:', latestDateStr)
        now = datetime.now()
        nowstr = now.strftime('%Y%m%d%H')
        if (latestDateStr != nowstr):
            is_update = True
    if (is_update):
        # 更新
        print('update')
        try:
            data = ytutils.ytapi_search_channelId(channel_id)
            ddbutils.registVideoListV2(data, True)
            urls = data['videos']['urls']
            titles = data['videos']['titles']
        except Exception as e:
            print('[WARN]', e)
            urls = v_list['urls']
            titles = v_list['titles']
    else:
        urls = v_list['urls']
        titles = v_list['titles']
    # n バリデーション
    if len(urls) <= n:
        return URL_404
    print(titles[n])
    return urls[n], titles[n]


def getVideoPage(url):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as res:
        body = res.read().decode('utf-8')
    return body


def get_ttl():
    start = datetime.now()
    expiration_date = start + timedelta(minutes=15)
    return round(expiration_date.timestamp())
