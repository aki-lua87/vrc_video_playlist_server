# VRCからコールするためにGET+動画をレスポンス
import os
# import urllib.request
import boto3
from datetime import datetime

import ddbutils
import ytutils
# import urllib.parse

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['VRC_VIDEO_TABLE'])

s3 = boto3.resource('s3')
s3_bucket = os.environ['S3_PUBLIC_BUCKET']

cf_domain = os.environ['CF_DOMAIN']


# def main(event, context):
#     print('event:', event)
#     httpMethod = event.get('httpMethod')
#     print('httpMethod:', httpMethod)
#     queryStringParameters = event.get('queryStringParameters')
#     query = queryStringParameters.get('q', '')
#     query = query.strip()
#     print('query:', query)

#     record = ddbutils.getQueryVideoList(query)
#     isExecIndexCreate = record.get('is_exec_index_create', True)
#     latestDateStr = record.get('latest_update', 'NoData')
#     print('latestDateStr:', latestDateStr)
#     print('isExecIndexCreate:', isExecIndexCreate)

#     now = datetime.datetime.now()
#     nowstr = now.strftime('%Y%m%d%H')
#     encodeWord = urllib.parse.quote(query)
#     rurl = f'{cf_domain}/yt/word/{encodeWord}.mp4'
#     print(rurl)
#     if (latestDateStr != nowstr):
#         # 更新
#         print('update and create')
#         data = ytutils.ytapi_search_query(query)
#         ddbutils.registQueryVideoList(data, False)
#         _ = call_create_video_api(query)
#     else:
#         if isExecIndexCreate:
#             # 非更新(APIコールのみ)
#             print('only create')
#             _ = call_create_video_api(query)
#             updateChannelUpdateDone(query)
#         else:
#             print('s3 get')
#     return {
#         'headers': {
#             "Content-type": "text/html; charset=utf-8",
#             "Access-Control-Allow-Origin": "*",
#             "location": rurl
#         },
#         'statusCode': 302,
#         'body': "",
#     }


# # リスト動画作成APIをコール
# def call_create_video_api(query):
#     url = f'https://v9kt9fos4k.execute-api.ap-northeast-1.amazonaws.com/dev/create/list/search?q={query}'
#     req = urllib.request.Request(url)
#     with urllib.request.urlopen(req):
#         print(f'call {url}')
#     print(f'channel_id {query} done')
#     return


# # 動画作成済みフラグ
# def updateChannelUpdateDone(query):
#     table.update_item(
#         Key={
#             'user_id': 'list_yt_query',
#             'video_id': query
#         },
#         UpdateExpression="set is_exec_index_create=:ieic",
#         ExpressionAttributeValues={
#             ':ieic': False,
#         },
#         ReturnValues="UPDATED_NEW"
#     )


def main(event, context):
    print('event:', event)
    httpMethod = event.get('httpMethod')
    ua = event.get('headers').get('User-Agent', '')
    print('httpMethod:', httpMethod)
    print('User-Agent:', ua)
    queryStringParameters = event.get('queryStringParameters')
    query = queryStringParameters.get('q', '')
    query = query.strip()
    print('query:', query)
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
