# VRCからコールするためにGET+動画をレスポンス
import json
import os
import urllib.request
import boto3
import base64
from datetime import datetime

import ddbutils
import ytutils

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['VRC_VIDEO_TABLE'])

s3 = boto3.resource('s3')
s3_bucket = os.environ['S3_PUBLIC_BUCKET']

cf_domain = os.environ['CF_DOMAIN']

PC_UA1 = 'Mozilla/5.0'
PC_UA2 = 'NSPlayer'
QUEST_UA = 'stagefright'
PC_AE = 'identity'  # 'Accept-Encoding': 'identity'
LOADER_UA = 'UnityPlayer'  # stringLoaderはこれ？


def main(event, context):
    MODE = "v1"
    print('event:', event)
    httpMethod = event.get('httpMethod')
    ua = event.get('headers').get('User-Agent', '')
    print('httpMethod:', httpMethod)
    print('User-Agent:', ua)
    channel_id = event['pathParameters'].get('channel_id')
    channel_id = channel_id.strip()
    print('channel_id:', channel_id)
    queryStringParameters = event.get('queryStringParameters')
    if queryStringParameters is not None:
        MODE = queryStringParameters.get('version', 'v1')
    if (MODE == 'v2'):
        videos = getVideoURL_V2(channel_id)
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
    else:
        if LOADER_UA in ua:
            # StringLoaderからなら文字列を返す
            titles = getVideoURL(channel_id)
            return {
                'headers': {
                    "Content-Type": "text/plain; charset=utf-8",
                    "Access-Control-Allow-Origin": "*"
                },
                'statusCode': 200,
                'body': ','.join(titles),
            }
    isExist = ddbutils.isExistChannelID(channel_id)
    if not isExist:
        print('does not exist', event)
        return base64.b64encode('video not exist')
    record = ddbutils.getVideoList(channel_id)
    isExecIndexCreate = record.get('is_exec_index_create', True)
    latestDateStr = record.get('latest_update', 'NoData')
    print('latestDateStr:', latestDateStr)
    print('isExecIndexCreate:', isExecIndexCreate)
    now = datetime.now()
    nowstr = now.strftime('%Y%m%d%H')
    rurl = f'{cf_domain}/yt/list/{channel_id}.mp4'
    print(rurl)
    try:
        if (latestDateStr != nowstr):
            # 更新
            print('update and create')
            data = ytutils.ytapi_search_channelId(channel_id)
            ddbutils.registVideoListV2(data, False)
            _ = call_create_video_api(channel_id)
        else:
            if isExecIndexCreate:
                # 非更新(APIコールのみ)
                print('only create')
                _ = call_create_video_api(channel_id)
                updateChannelUpdateDone(channel_id)
            else:
                print('s3 get')
    except Exception as e:
        print('[WARN] 更新失敗', e)
    return {
        'headers': {
            "Content-type": "text/html; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
            "location": rurl
        },
        'statusCode': 302,
        'body': "",
    }


# リスト動画作成APIをコール
def call_create_video_api(channel_id):
    url = f'https://v9kt9fos4k.execute-api.ap-northeast-1.amazonaws.com/dev/create/video/{channel_id}'
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req):
        print(f'call {url}')
    print(f'channel_id {channel_id} done')
    return


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


def getVideoURL(channel_id):
    # Videoのlistを取得
    v_list = ddbutils.getVideoList(channel_id)
    if v_list is None:
        return None
    # 更新有無の確認
    latestDateStr = v_list.get('latest_update', 'NoData')
    print('latestDateStr:', latestDateStr)
    now = datetime.now()
    nowstr = now.strftime('%Y%m%d%H')
    if (latestDateStr != nowstr):
        # 更新
        print('update')
        try:
            data = ytutils.ytapi_search_channelId(channel_id)
            ddbutils.registVideoListV2(data, True)
            titles = data['videos']['titles']
        except Exception as e:
            print('[WARN]', e)
            titles = v_list['titles']
    else:
        titles = v_list['titles']
    return titles


def getVideoURL_V2(channel_id):
    # Videoのlistを取得
    v_list = ddbutils.getVideoList(channel_id)
    if v_list is None:
        return None
    # 更新有無の確認
    latestDateStr = v_list.get('latest_update', 'NoData')
    print('latestDateStr:', latestDateStr)
    now = datetime.now()
    nowstr = now.strftime('%Y%m%d%H')
    if (latestDateStr != nowstr):
        # 更新
        print('update')
        try:
            data = ytutils.ytapi_search_channelId(channel_id)
            ddbutils.registVideoListV2(data, True)
            videos = data['videos']

        except Exception as e:
            print('[WARN]', e)
            videos = v_list
    else:
        videos = v_list
    return videos
