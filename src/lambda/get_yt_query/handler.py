import os
import json
import boto3
import datetime

import ddbutils
import ytutils

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['VRC_VIDEO_TABLE'])
cf_domain = os.environ['CF_DOMAIN']


def main(event, context):
    print('event:', event)
    queryStringParameters = event.get('queryStringParameters')
    httpMethod = event.get('httpMethod')
    print('httpMethod:', httpMethod)
    if queryStringParameters is None:
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
    before = queryStringParameters.get('n', 0)
    query = queryStringParameters.get('q', '')
    b_int = int(before)
    print(query, before)
    try:
        url = getVideoURL(b_int, query)
    except BaseException:
        url = f'{cf_domain}/nf.mp4'
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
    # Videoのlistを取得
    v_list = ddbutils.getQueryVideoList(q)
    # 更新有無の確認
    if v_list is not None:
        latestDateStr = v_list.get('latest_update', 'NoData')
    else:
        latestDateStr = 'Nodata'
    print('latestDateStr:', latestDateStr)
    now = datetime.datetime.now()
    nowstr = now.strftime('%Y%m%d%H')
    if (latestDateStr != nowstr):
        # 更新
        print('update')
        try:
            data = ytutils.ytapi_search_query(q)
        except Exception as e:
            print('[WARN] 更新失敗', e)
            return v_list['urls'][n]
        ddbutils.registQueryVideoList(data, True)
        urls = data['videos']['urls']
        titles = data['videos']['titles']
    else:
        urls = v_list['urls']
        titles = v_list['titles']
    if len(urls) < n:
        return f'{cf_domain}/nf.mp4'
    print(urls[n], titles[n])
    return urls[n]
