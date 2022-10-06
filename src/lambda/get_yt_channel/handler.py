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
PC_AE = '*'  # 'Accept-Encoding': '*'

cf_domain = os.environ['CF_DOMAIN']
URL_404 = f'{cf_domain}/nf.mp4'


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
    url = getVideoURL(channel_id, b_int)
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
    ttl = get_ttl()
    ddbutils.registQuestURL(url, quest_url, ttl)
    return quest_url


def getVideoURL(channel_id, n):
    # Videoのlistを取得
    v_list = ddbutils.getVideoList(channel_id)
    # 更新有無の確認
    latestDateStr = v_list.get('latest_update', 'NoData')
    print('latestDateStr:', latestDateStr)
    now = datetime.now()
    nowstr = now.strftime('%Y%m%d%H')
    if (latestDateStr != nowstr):
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
    return urls[n]


def getVideoPage(url):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as res:
        body = res.read().decode('utf-8')
    return body


def get_ttl():
    start = datetime.now()
    expiration_date = start + timedelta(minutes=15)
    return round(expiration_date.timestamp())
