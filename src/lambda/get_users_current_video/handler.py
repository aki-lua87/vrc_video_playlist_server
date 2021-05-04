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
    queryStringParameters = event.get('queryStringParameters')
    if user_id == None or queryStringParameters == None:
        return {
            'headers': { 
                    "Access-Control-Allow-Origin": "*"
                },
            'statusCode': 400,
            'body': json.dumps(
                {
                    'error': 'bad request [1]'
                }
            )
        }
    before = queryStringParameters.get('b')
    urls = getCurrentListVideoURL(user_id)
    b_int = int(before)
    if b_int >= len(urls):
        return {
            'headers': { 
                    "Access-Control-Allow-Origin": "*"
                },
            'statusCode': 400,
            'body': json.dumps(
                {
                    'error': 'bad request [2]'
                }
            )
        }
    body = getVideoPage(urls[b_int]['url'])
    return {
        'headers': { 
                "Content-type": "text/html; charset=utf-8",
                "Access-Control-Allow-Origin": "*"
            },
        'statusCode': 200,
        'body': body,
    }


def getCurrentListVideoURL(user_id):
    # カレントのVideoIDを取得
    video_id = GetCurrentVideoID(user_id)
    if video_id == None:
        return None
    # VideoIDのlistを取得
    v_list = GetCurrentVideoList(user_id, video_id)
    if v_list == None:
        return None
    res = []
    for i in range(len(v_list['url'])):
        res.append({'url': v_list['url'][i],
                   'description': v_list['description'][i]})
    return res

def GetCurrentVideoID(user_id):
    response = table.get_item(
        Key={
            'user_id': 'current',
            'video_id': user_id
        }
    )
    record = response.get('Item')
    if record == None:
        return None
    return record.get('current')

def GetCurrentVideoList(user_id, video_id):
    response = table.get_item(
        Key={
            'user_id': 'list',
            'video_id': f'{user_id}_{video_id}'
        }
    )
    record = response.get('Item')
    if record == None:
        return None
    return record

# youtubeの内容をそのまま返す
def getVideoPage(url):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as res:
        body = res.read().decode('utf-8')
    return body