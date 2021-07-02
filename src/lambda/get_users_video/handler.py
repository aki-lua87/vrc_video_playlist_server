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
    httpMethod = event.get('httpMethod')
    if user_id == None or video_id == None:
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
    isLimit = checkRateLimit(user_id, video_id)
    if not isLimit:
        return {
            'headers': { 
                    "Access-Control-Allow-Origin": "*"
                },
            'statusCode': 400,
            'body': json.dumps(
                {
                    'error': 'Rate Limit'
                }
            )
        }
    url = getVideoURL(user_id, video_id)
    if httpMethod == 'HEAD':
        print('HEAD Return')
        return {
            'headers': { 
                    "Content-type": "text/html; charset=utf-8",
                    "Access-Control-Allow-Origin": "*",
                    "location": url
                },
            'statusCode': 302,
            'body': "",
        }
    body = getVideoPage(url)
    return {
        'headers': { 
                "Content-type": "text/html; charset=utf-8",
                "Access-Control-Allow-Origin": "*"
            },
        'statusCode': 200,
        'body': body,
    }


def getVideoURL(user_id, video_id):
    response = table.get_item(
        Key={
            'user_id': user_id,
            'video_id': video_id
        }
    )
    record = response.get('Item')
    if record == None:
        return False
    print(record)
    return record.get('url')

def checkRateLimit(user_id, video_id):
    return True

# youtubeの内容をそのまま返す
def getVideoPage(url):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as res:
        body = res.read().decode('utf-8')
    return body