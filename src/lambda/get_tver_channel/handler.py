import os
from re import search
import urllib.request
import json
import boto3

import ddbutils

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['VRC_VIDEO_TABLE'])


def main(event, context):
    print('event:', event)
    attribute = event['pathParameters'].get('attribute')
    attribute = attribute.strip()
    queryStringParameters = event.get('queryStringParameters')
    httpMethod = event.get('httpMethod')
    print('attribute:', attribute)
    print('httpMethod:', httpMethod)
    if attribute is None or queryStringParameters is None:
        return {
            'headers': {
                "Access-Control-Allow-Origin": "*"
            },
            'statusCode': 400,
            'body': json.dumps(
                {
                    'result': 'NG',
                    'error': 'bad request [1]'
                }
            )
        }
    # 文字列指定でもいけるように
    searchWord = queryStringParameters.get('search', '')
    if searchWord == '':
        before = queryStringParameters.get('n', '0')
        b_int = int(before)
        url = getVideoURL(attribute, b_int)
    else:
        url = getSearchVideoURL(attribute, searchWord)
    if httpMethod == 'HEAD':
        print('HEAD Return')
        return {
            'headers': {
                "Content-type": "text/html; charset=utf-8",
                "Access-Control-Allow-Origin": "*",
                "location": url
            },
            'statusCode': 302,
            'body': "",
        }
    # TODO: Questはこれでいけるだろうか
    body = getVideoPage(url)
    return {
        'headers': {
            "Content-type": "text/html; charset=utf-8",
            "Access-Control-Allow-Origin": "*"
        },
        'statusCode': 200,
        'body': body,
    }


def getVideoURL(attribute, n):
    # Videoのlistを取得
    v_list = ddbutils.getTVer(attribute)
    urls = v_list['urls']
    titles = v_list['titles']
    if len(urls) < n:
        # 要素超えはエラー動画へ
        return ''
    print(urls[n], titles[n])
    return urls[n]


def getSearchVideoURL(attribute, text):
    # Videoのlistを取得
    v_list = ddbutils.getTVer(attribute)
    urls = v_list['urls']
    titles = v_list['titles']
    for index, title in enumerate(titles):
        if(text in title):
            return urls[index]
    # スカの場合はエラー動画へ
    return ''


def getVideoPage(url):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as res:
        body = res.read().decode('utf-8')
    return body
