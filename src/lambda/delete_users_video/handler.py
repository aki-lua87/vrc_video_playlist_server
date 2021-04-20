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
    video_id = event['queryStringParameters'].get('video_id')
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
    print('user_id:::',user_id)
    print('video_id:::',video_id)
    deleteVideo(user_id, video_id)
    return {
        'headers': { 
                "Content-type": "text/html; charset=utf-8",
                "Access-Control-Allow-Origin": "*"
            },
        'statusCode': 200,
        'body': json.dumps({}),
    }


def deleteVideo(user_id, video_id):
    response = table.delete_item(
        Key={
            'user_id': user_id,
            'video_id': video_id
        }
    )
    print(response)
    return
