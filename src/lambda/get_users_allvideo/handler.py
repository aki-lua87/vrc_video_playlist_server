import os
import time
import urllib.request
import json
import boto3
import uuid
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb')
table    = dynamodb.Table(os.environ['VRC_VIDEO_TABLE'])

def main(event, context):
    user_id = event['pathParameters'].get('user_id')
    if user_id == None:
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
    allurls = getAllVideoURL(user_id)

    return {
        'headers': { 
                "Access-Control-Allow-Origin": "*"
            },
        'statusCode': 200,
        'body': json.dumps(allurls),
    }


def getAllVideoURL(user_id):
    response = table.query(KeyConditionExpression=Key('user_id').eq(user_id))
    print(response)
    record = response.get('Items')
    if record == None:
        return 'None'
    # user_id/userのレコードを削除する必要あり
    return record
