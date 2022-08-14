import os
import urllib.request
import boto3

import ddbutils
from bs4 import BeautifulSoup

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['VRC_VIDEO_TABLE'])
cf_domain = os.environ['CF_DOMAIN']
tverurl = 'https://tver.jp'


def main(event, context):
    print('event:', event)
    queryStringParameters = event.get('queryStringParameters')
    httpMethod = event.get('httpMethod')
    print('httpMethod:', httpMethod)
    if queryStringParameters is None:
        return {
            'headers': {
                "Content-type": "text/html; charset=utf-8",
                "Access-Control-Allow-Origin": "*",
                "location": f'{cf_domain}/nf.mp4'
            },
            'statusCode': 302,
            'body': "",
        }
    # 検索文字列を取得
    searchWord = queryStringParameters.get('search', '')
    lp_url = getSearchVideoURL('lineup', searchWord)
    print(f'lp_url:{lp_url}')
    lp_html = getLP(lp_url)
    url = getTVerURLforLPhtml(lp_html)
    print(f'url:{url}')
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


def getSearchVideoURL(attribute, text):
    # DynamoDBより対象の番組を取得
    v_list = ddbutils.getTVer2(attribute, text)
    if v_list is None:
        # スカの場合はエラー動画へ
        print(f'{attribute} {text} none')
        return f'{cf_domain}/nf.mp4'
    v = v_list[0]
    url = v['url']
    title = v['title']
    print(url, title)
    return f'{tverurl}{url}'


def getLP(url):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as res:
        body = res.read().decode('utf-8')
    return body


def getTVerURLforLPhtml(html):
    try:
        # 無理やりなのでなんかいつか考えること
        soup = BeautifulSoup(html, "html.parser")
        # for liements in soup.select('li'):
        url = soup.find('link').get('href')
        return f'{url}'
    except BaseException:
        print('getTVerURLforLPhtml BaseException')
        return f'{cf_domain}/nf.mp4'
