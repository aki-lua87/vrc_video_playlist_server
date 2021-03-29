import os
import time
import urllib.request
import json
import boto3

# メタ情報
gss_api_url = os.environ['GSS_API_URL']


# Lambdaエントリポイント
def main(event, context):
    # クエリ文字列を読み取り
    key = event['queryStringParameters'].get('key')

    # GSSよりURLを取得
    video_url = get_video_url(key)
    print(video_url)
    url = json.loads(video_url)
    print(url)

    # 動画サイトよりHTMLを取得
    body = get_video_page(url)
    return {
        'headers': { "Content-type": "text/html; charset=utf-8" },
        'statusCode': 200,
        'body': body,
    }

# youtubeの内容をそのまま返す
def get_video_page(url):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as res:
        body = res.read().decode('utf-8')
    return body

# GSSよりURLを取得
def get_video_url(key):
    url = gss_api_url+str(key)
    print(url)
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as res:
        body = res.read().decode('utf-8')
    return body