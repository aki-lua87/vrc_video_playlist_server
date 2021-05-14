# VRCからコールするためにGET+動画をレスポンス
import os
import time
import urllib.request
import json
import boto3
import uuid
import base64

dynamodb = boto3.resource('dynamodb')
table    = dynamodb.Table(os.environ['VRC_VIDEO_TABLE'])

def main(event, context):
    user_id = event['path'].get('user_id')
    video_id = event['path'].get('vid')
    # ユーザチェック
    isExist = isUserExist(user_id)
    if not isExist:
        return {
            'headers': { 
                    "Access-Control-Allow-Origin": "*"
                },
            'statusCode': 400,
            'body': json.dumps(
                {
                    'error': 'user not exist'
                }
            )
        }
    # videoのチェック
    isExist = isVideoExist(user_id, video_id)
    if not isExist:
        return {
            'headers': { 
                    "Access-Control-Allow-Origin": "*"
                },
            'statusCode': 400,
            'body': json.dumps(
                {
                    'error': 'video not exist'
                }
            )
        }
    # 切り替え実行
    change(user_id, video_id)
    body = call_create_video_api(user_id)
    return base64.b64encode(body)
    # {
    #     'headers': {
    #             "Content-type": "text/html; charset=utf-8",
    #             "Access-Control-Allow-Origin": "*"
    #         },
    #     'statusCode': 200,
    #     'body': body,
    # }

def change(user_id,video_id):
    table.put_item(
        Item={
            'user_id': 'current',
            'video_id': f'{user_id}',
            'current':video_id
        }
    )

def isUserExist(user_id):
    response = table.get_item(
        Key={
            'user_id': 'user',
            'video_id': user_id
        }
    )
    isExistRecord = response.get('Item')
    if isExistRecord == None:
        return False
    return True

def isVideoExist(user_id, video_id):
    response = table.get_item(
        Key={
            'user_id': user_id,
            'video_id': video_id
        }
    )
    isExistRecord = response.get('Item')
    if isExistRecord == None:
        return False
    return True

def call_create_video_api(user_id):
    url = f'https://v9kt9fos4k.execute-api.ap-northeast-1.amazonaws.com/dev/user/{user_id}/create/video/current'
    print(url)
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as res:
        body = res.read() # .decode('utf-8')
    print(f'user_id {user_id} done')
    return body