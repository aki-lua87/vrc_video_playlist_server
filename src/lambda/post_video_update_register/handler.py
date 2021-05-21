import os
import time
import urllib.request
import json
import boto3
import uuid

dynamodb = boto3.resource('dynamodb')
table    = dynamodb.Table(os.environ['VRC_VIDEO_TABLE'])

def main(event, context):
    user_id = event['pathParameters'].get('user_id')
    video_id = event['pathParameters'].get('video_id')
    body = json.loads(event['body'])
    channel_id = body.get('channel_id')
    description = body.get('description')
    # 引数チェック
    if user_id == None or video_id == None or channel_id == None:
        return {
            'headers': { 
                    "Access-Control-Allow-Origin": "*"
                },
            'statusCode': 400,
            'body': json.dumps(
                {
                    'error': 'bad request'
                }
            )
        }
    # ビデオチェック
    isExist = isVideoExist(user_id,video_id)
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
    # アップデート用レコードを追加
    registUpdate(user_id,video_id,channel_id,description)
    return {
        'headers': {
                "Access-Control-Allow-Origin": "*"
            },
        'statusCode': 200,
        'body': json.dumps({}),
    }

def registUpdate(user_id,video_id,channel_id,description):
    table.put_item(
        Item={
            'user_id': 'update',
            'video_id': f'{user_id}_{video_id}',
            'channel_id':channel_id,
            'description':description
        }
    )

def isVideoExist(user_id,video_id):
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
