# VRCからコールするためにGET+動画をレスポンス
import os
import urllib.request
import boto3
import base64
import datetime

import ddbutils
import ytutils

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['VRC_VIDEO_TABLE'])

s3 = boto3.resource('s3')
s3_bucket = os.environ['S3_PUBLIC_BUCKET']

cf_domain = os.environ['CF_DOMAIN']


def main(event, context):
    print('event:', event)
    httpMethod = event.get('httpMethod')
    print('httpMethod:', httpMethod)
    # if httpMethod == 'HEAD':
    #     print('HEAD Return')
    #     return {
    #         'headers': {
    #             "Content-type": "text/html; charset=utf-8",
    #             "Access-Control-Allow-Origin": "*",
    #         },
    #         'statusCode': 200,
    #         'body': "",
    #     }
    # channel_id = event['path'].get('channel_id')
    channel_id = event['pathParameters'].get('channel_id')
    channel_id = channel_id.strip()
    print('channel_id:', channel_id)
    isExist = ddbutils.isExistChannelID(channel_id)
    if not isExist:
        print('does not exist', event)
        return base64.b64encode('video not exist')
    record = ddbutils.getVideoList(channel_id)
    isExecIndexCreate = record.get('is_exec_index_create', True)
    latestDateStr = record.get('latest_update', 'NoData')
    print('latestDateStr:', latestDateStr)
    print('isExecIndexCreate:', isExecIndexCreate)

    now = datetime.datetime.now()
    nowstr = now.strftime('%Y%m%d%H')
    rurl = f'{cf_domain}/yt/list/{channel_id}.mp4'
    print(rurl)
    if (latestDateStr != nowstr):
        # 更新
        print('update and create')
        data, _ = ytutils.getRSS(channel_id)
        _, urls, descriptions = ytutils.scrapingRSS(data)
        ddbutils.registVideoList(channel_id, urls, descriptions, False)
        _ = call_create_video_api(channel_id)
    else:
        if isExecIndexCreate:
            # 非更新(APIコールのみ)
            print('only create')
            _ = call_create_video_api(channel_id)
            updateChannelUpdateDone(channel_id)
        else:
            print('s3 get')
            # TODO: リダイレクト
            _ = get_s3_video(s3_bucket, channel_id)
    return {
        'headers': {
            "Content-type": "text/html; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
            "location": rurl
        },
        'statusCode': 302,
        'body': "",
    }
    # return base64.b64encode(body)


# リスト動画作成APIをコールし動画を取得
def call_create_video_api(channel_id):
    url = f'https://v9kt9fos4k.execute-api.ap-northeast-1.amazonaws.com/dev/create/video/{channel_id}'
    print(url)
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as res:
        body = res.read()
    print(f'channel_id {channel_id} done')
    return body


# S3から動画を取得
def get_s3_video(bucket_name, channel_id):
    path = 'yt/channel/'+channel_id+'.mp4'
    print('getS3Video', bucket_name, path)
    bucket = s3.Bucket(bucket_name)
    obj = bucket.Object(path)
    response = obj.get()
    body = response['Body'].read()
    return body


# 動画作成済みフラグ
def updateChannelUpdateDone(channel_id):
    table.update_item(
        Key={
            'user_id': 'list_yt_ch',
            'video_id': channel_id
        },
        UpdateExpression="set is_exec_index_create=:ieic",
        ExpressionAttributeValues={
            ':ieic': False,
        },
        ReturnValues="UPDATED_NEW"
    )
