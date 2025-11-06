# VRCからコールするためにGET+動画をレスポンス
import os
# import urllib.request
import boto3
from datetime import datetime

import ddbutils
import ytutils

import json
# import urllib.parse

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['VRC_VIDEO_TABLE'])

s3 = boto3.resource('s3')
s3_bucket = os.environ['S3_PUBLIC_BUCKET']

cf_domain = os.environ['CF_DOMAIN']


def main(event, context):
    print('event:', event)
    httpMethod = event.get('httpMethod')
    ua = event.get('headers').get('User-Agent', '')
    print('httpMethod:', httpMethod)
    print('User-Agent:', ua)
    queryStringParameters = event.get('queryStringParameters')
    query = queryStringParameters.get('q', '')
    MODE = queryStringParameters.get('version', 'v1')
    query = query.strip()
    print('query:', query)
    if (MODE == 'v2'):
        videos = getVideoURL_V2(query)
        # videos をJSONに変換する
        json_videos = json.dumps(videos, ensure_ascii=False)
        return {
            'headers': {
                "Content-Type": "text/plain; charset=utf-8",
                "Access-Control-Allow-Origin": "*"
            },
            'statusCode': 200,
            'body': json_videos,
        }
    titles = getVideoURL(query)
    print('titles:', titles)
    return {
        'headers': {
            "Content-Type": "text/plain; charset=utf-8",
            "Access-Control-Allow-Origin": "*"
        },
        'statusCode': 200,
        'body': ','.join(titles),
    }


def getVideoURL(q):
    is_update = False
    titles = []
    # Videoのlistを取得
    v_list = ddbutils.getQueryVideoList(q)
    if v_list is None:
        print('v_list is None')
        is_update = True
    else:
        # 更新有無の確認
        latestDateStr = v_list.get('latest_update', 'NoData')
        print('latestDateStr:', latestDateStr)
        now = datetime.now()
        nowstr = now.strftime('%Y%m%d%H')
        if (latestDateStr != nowstr):
            print('latestDateStr != nowstr')
            is_update = True
    if is_update:
        # 更新
        print('update')
        data = ytutils.ytapi_search_query(q)
        ddbutils.registQueryVideoList(data)
        titles = data['videos']['titles']
    else:
        titles = v_list['titles']
    return titles


def getVideoURL_V2(q):
    is_update = False
    titles = []
    # Videoのlistを取得
    v_list = ddbutils.getQueryVideoList(q)
    if v_list is None:
        print('v_list is None')
        is_update = True
    else:
        # 更新有無の確認
        latestDateStr = v_list.get('latest_update', 'NoData')
        print('latestDateStr:', latestDateStr)
        now = datetime.now()
        nowstr = now.strftime('%Y%m%d%H')
        if (latestDateStr != nowstr):
            print('latestDateStr != nowstr')
            is_update = True
    if is_update:
        # 更新
        print('update')
        data = ytutils.ytapi_search_query(q)
        ddbutils.registQueryVideoList(data)
        titles = data['videos']
    else:
        titles = v_list
    return titles
