# 動作検証版バックエンドスプレッドシート版API
import os
import time
import urllib.request
import json
import boto3
import threading
import concurrent.futures
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb')
table    = dynamodb.Table(os.environ['VRC_VIDEO_TABLE'])

# Lambdaエントリポイント
def main(event, context):
    print('start')
    # 全ユーザを取得
    users = get_all_user()
    for user in users:
        try:
            call_create_video_api(user.get('video_id'))
        except Exception as e:
            print('[ERROR]',user,e)
    return 

def call_create_video_api(user_id):
    # video_idにユーザIDが格納されている
    # user_id = user.get('video_id')
    url = f'https://v9kt9fos4k.execute-api.ap-northeast-1.amazonaws.com/dev/user/{user_id}/create/video/list'
    print(url)
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as res:
        body = res.read().decode('utf-8')
    print(f'user_id {user_id} done')
    return body

def get_all_user():
    response = table.query(KeyConditionExpression=Key('user_id').eq('user'))
    # print(response)
    record = response.get('Items')
    if record == None:
        return []
    return record
