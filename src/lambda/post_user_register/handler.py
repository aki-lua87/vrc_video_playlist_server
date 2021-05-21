import os
import time
import urllib.request
import json
import boto3
import uuid

dynamodb = boto3.resource('dynamodb')
table    = dynamodb.Table(os.environ['VRC_VIDEO_TABLE'])
video_list_url = os.environ['VIDEO_LIST_URL']

def main(event, context):
    user_id = createUserID()
    registerUser(user_id)
    url = f'{video_list_url}/{user_id}/video.mp4'
    return {
        'headers': { 
                "Access-Control-Allow-Origin": "*"
            },
        'statusCode': 200,
        'body': json.dumps(
            {
                'user_id': user_id,
                'video_list_url': url
            }
        )
    }

def createUserID():
    return str(uuid.uuid4())[0:8]

def registerUser(user_id):
    table.put_item(
        Item={
            "user_id": 'user',
            "video_id": user_id
        }
    )