import os
import urllib.request
import boto3

import ddbutils

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['VRC_VIDEO_TABLE'])
cf_domain = os.environ['CF_DOMAIN']


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
                "Content-type": "text/html; charset=utf-8",
                "Access-Control-Allow-Origin": "*",
                "location": f'{cf_domain}/nf.mp4'
            },
            'statusCode': 302,
            'body': "",
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
    # TODO: Questはこれでいけるだろうか->いけないらしい
    # body = getVideoPage(url)
    return {
        'headers': {
            "Content-type": "text/html; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
            "location": url
        },
        'statusCode': 302,
        'body': "",
    }


def getVideoURL(attribute, n):
    # Videoのlistを取得
    v_list = ddbutils.getTVer(attribute)
    urls = v_list['urls']
    titles = v_list['titles']
    if len(urls) < n:
        # 要素超えはエラー動画へ
        return f'{cf_domain}/nf.mp4'
    print(urls[n], titles[n])
    return urls[n]


def getSearchVideoURL(attribute, text):
    # Videoのlistを取得
    v_list = ddbutils.getTVer(attribute)
    urls = v_list['urls']
    titles = v_list['titles']
    for index, title in enumerate(titles):
        if(text in title):
            print(urls[index], title)
            return urls[index]
    # スカの場合はエラー動画へ
    return f'{cf_domain}/nf.mp4'


def getVideoPage(url):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as res:
        body = res.read().decode('utf-8')
    return body
