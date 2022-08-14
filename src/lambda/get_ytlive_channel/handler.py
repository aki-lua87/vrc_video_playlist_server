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
    channel_id = event['pathParameters'].get('channel_id')
    channel_id = channel_id.strip()
    httpMethod = event.get('httpMethod')
    print('channel_id:', channel_id)
    print('httpMethod:', httpMethod)
    if channel_id is None:
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
    url = getVideoURL(channel_id)
    if url == '':
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


def getVideoURL(channel_id):
    # Videoのlistを取得
    v_list = ddbutils.getVideoList(channel_id)
    # 更新有無の確認
    latestDateStr = v_list.get('latest_update', 'NoData')
    print('latestDateStr:', latestDateStr)
    now = datetime.datetime.now()
    nowstr = now.strftime('%Y%m%d%H')
    if (latestDateStr != nowstr):
        # 更新
        print('update')
        data = ytutils.ytapi_search_channelId(channel_id)
        ddbutils.registVideoListV2(data, True)
        url = data['live']['title']
        title = data['live']['url']
    else:
        url = v_list['live']
        title = '未実装'
    print(url, title)
    return url
