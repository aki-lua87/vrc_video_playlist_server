# VRCからコールするためにGET+動画をレスポンス
import os
import urllib.request
import boto3
import base64

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['VRC_VIDEO_TABLE'])

s3 = boto3.resource('s3')
s3_bucket = os.environ['S3_PUBLIC_BUCKET']


def main(event, context):
    channel_id = event['path'].get('channel_id')
    isExecUpdate, isExist = GetExecVideoListCreate(channel_id)
    if not isExist:
        print('does not exist', event)
        return base64.b64encode('video not exist')
    if isExecUpdate:
        print('create')
        # APIの中で動画保存まで実施
        body = call_create_video_api(channel_id)
        # put_s3_video(s3_bucket,body,channel_id)
        updateChannelUpdateDone(channel_id)
    else:
        print('s3 get')
        body = get_s3_video(s3_bucket, channel_id)
    return base64.b64encode(body)

# リスト動画作成APIをコールし動画を取得


def call_create_video_api(channel_id):
    url = f'https://v9kt9fos4k.execute-api.ap-northeast-1.amazonaws.com/dev/create/video/{channel_id}'
    print(url)
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as res:
        body = res.read()  # .decode('utf-8')
    print(f'channel_id {channel_id} done')
    return body

# channel情報と更新有無を取得


def GetExecVideoListCreate(channel_id):
    response = table.get_item(
        Key={
            'user_id': 'yt_channnel_id',
            'video_id': f'{channel_id}',
        }
    )
    record = response.get('Item')
    if record is None:
        return False, False
    isExec = record.get('index_create')
    return isExec, True

# channel動画一覧を取得


def getVideoURLList(channel_id):
    # Videoのlistを取得
    v_list = GetVideoList(channel_id)
    if v_list is None:
        return None
    res = []
    for i in range(len(v_list['urls'])):
        res.append({'urls': v_list['urls'][i],
                    'titles': v_list['titles'][i]})
    return res


def GetVideoList(channel_id):
    response = table.get_item(
        Key={
            'user_id': 'list_yt_ch',
            'video_id': f'{channel_id}',
        }
    )
    record = response.get('Item')
    if record is None:
        return None
    return record

# 動画をS3に保存


def put_s3_video(bucket_name, file, channel_id):
    print('put_s3')
    bucket = s3.Bucket(bucket_name)
    bucket.upload_file(file, 'yt/channel/'+channel_id+'.mp4')

# S3から動画を取得


def get_s3_video(bucket_name, channel_id):
    path = 'yt/channel/'+channel_id+'.mp4'
    print('getS3Video', bucket_name, path)
    bucket = s3.Bucket(bucket_name)
    obj = bucket.Object(path)
    response = obj.get()
    body = response['Body'].read()
    return body


def updateChannelUpdateDone(channel_id):
    table.put_item(
        Item={
            'user_id': 'yt_channnel_id',
            'video_id': channel_id,
            'author': '',
            'index_create': False
        }
    )
