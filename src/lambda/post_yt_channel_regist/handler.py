import os
import time
import urllib.request
import json
import boto3
import uuid
from boto3.dynamodb.conditions import Key
import xml.etree.ElementTree as ET

dynamodb = boto3.resource('dynamodb')
table    = dynamodb.Table(os.environ['VRC_VIDEO_TABLE'])

def main(event, context):
    body = json.loads(event['body'])
    channel_id = body.get('channel_id')
    # 引数チェック
    if channel_id == None:
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
    # channel_id登録チェック
    isExist,auther = isExistChannelID(channel_id)
    if isExist:
        # 存在する場合登録なしでOKを返却
        return {
            'headers': { 
                    "Access-Control-Allow-Origin": "*"
                },
            'statusCode': 200,
            'body': json.dumps(
                {
                    'result': 'OK',
                    'auther':auther
                }
            )
        }
    # チャンネル存在チェック & データ取得
    data, isValid = getData(channel_id)
    if not isValid:
        return {
            'headers': { 
                    "Access-Control-Allow-Origin": "*"
                },
            'statusCode': 400,
            'body': json.dumps(
                {
                    'result':'NG',
                    'error': 'channel not exist'
                }
            )
        }

    descriptions = []
    urls = []
    name = ""
    for child in data:
        if child.tag == '{http://www.w3.org/2005/Atom}author':
            for author in child:
                if author.tag == '{http://www.w3.org/2005/Atom}name':
                    name = child.find('{http://www.w3.org/2005/Atom}name').text
        if child.tag == '{http://www.w3.org/2005/Atom}entry':
            for childchild in child:
                if childchild.tag == '{http://www.w3.org/2005/Atom}title':
                    descriptions.append(child.find('{http://www.w3.org/2005/Atom}title').text)
                if childchild.tag == '{http://www.w3.org/2005/Atom}link':
                    urls.append(childchild.attrib['href'])


    # レコードを追加
    registChannel(channel_id, name)
    registVideoList(channel_id,urls,descriptions)
    # https://hoge/videos/yt/{channel_id}

    # OK
    return {
        'headers': {
                "Access-Control-Allow-Origin": "*"
            },
        'statusCode': 200,
        'body': json.dumps({'result':'OK','auther':name}), # Auther返すこと
    }

def isExistChannelID(channel_id):
    response = table.get_item(
        Key={
            'user_id': 'yt_channnel_id',
            'video_id': channel_id
        }
    )
    isExistRecord = response.get('Item')
    if isExistRecord == None:
        return False,""
    return True,isExistRecord.get('author')

def registChannel(channel_id,author):
    table.put_item(
        Item={
            'user_id': 'yt_channnel_id',
            'video_id': channel_id,
            'author': '',
            'index_create': True
        }
    )

def registVideoList(channel_id,video_urls,descriptions):
    table.put_item(
        Item={
            'user_id': 'list_yt_ch',
            'video_id': f'{channel_id}',
            'titles':descriptions,
            'urls':video_urls
        }
    )

def getData(channel_id):
    # ここTryCatch
    url = "https://www.youtube.com/feeds/videos.xml?channel_id="+channel_id
    body = getRssFeed(url)
    root = ET.fromstring(body)
    if len(root) == 0:
        return [], False
    return root, True

def getRssFeed(url):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as res:
        body = res.read().decode('utf-8')
    return body

