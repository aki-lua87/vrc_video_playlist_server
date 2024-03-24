import os
import json
import boto3
from datetime import datetime, timedelta

import ddbutils
import ytutils

PC_UA1 = 'Mozilla/5.0'
PC_UA2 = 'NSPlayer'
QUEST_UA = 'stagefright'
PC_AE = 'identity'  # 'Accept-Encoding': 'identity'

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['VRC_VIDEO_TABLE'])

cf_domain = os.environ['CF_DOMAIN']
URL_404 = f'{cf_domain}/nf.mp4'


def main(event, context):
    print('event:', event)
    queryStringParameters = event.get('queryStringParameters')
    httpMethod = event.get('httpMethod')
    ua = event.get('headers').get('User-Agent', '')
    ae = event.get('headers').get('Accept-Encoding', '')
    print('httpMethod:', httpMethod)
    print('User-Agent:', ua)
    if queryStringParameters is None:
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
    number_srt = queryStringParameters.get('n', 0)
    query = queryStringParameters.get('q', '')
    number = int(number_srt)
    url, title = getVideoURL(number, query)
    if QUEST_UA in ua:
        # Quest処理 urlを上書き
        print('Quest Request')
        # url = resolvURL(url)
    elif ae == PC_AE:
        # PC処理
        print('PC Request')
    else:
        # Other YTTL JSONを返却
        return {
            'headers': {
                "Content-type": "text/html; charset=utf-8",
                "Access-Control-Allow-Origin": "*",
            },
            'statusCode': 200,
            'body': '{"title":"' + title + '"}',
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


def getVideoURL(n, q):
    is_update = False
    # Videoのlistを取得
    v_list = ddbutils.getQueryVideoList(q)
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
    if is_update:
        # 更新
        print('update')
        data = ytutils.ytapi_search_query(q)
        ddbutils.registQueryVideoList(data)
        urls = data['videos']['urls']
        titles = data['videos']['titles']
    else:
        urls = v_list['urls']
        titles = v_list['titles']
    # n バリデーション
    if len(urls) <= n:
        print('404::', titles)
        return URL_404, 'Not Found'
    print(titles[n])
    return urls[n], titles[n]


def returnBadRequest():
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


def returnRedirect(url):
    return {
        'headers': {
            "Content-type": "text/html; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
            "location": url
        },
        'statusCode': 302,
        'body': "",
    }


def get_ttl():
    start = datetime.now()
    expiration_date = start + timedelta(minutes=15)
    return round(expiration_date.timestamp())


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
