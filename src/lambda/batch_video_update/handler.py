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
    videosInfo = getUpadteVideoList()
    if videosInfo == None:
        print('[ERROR] not data')
        return
    for videoInfo in videosInfo:
        try:
            u_v = videoInfo['video_id'].split('_')
            user_id = u_v[0]
            video_id = u_v[1]
            putLatestVideo(user_id,video_id,videoInfo['channel_id'])
        except Exception as e:
            print('ERROR',videoInfo,e)

def getUpadteVideoList():
    response = table.query(KeyConditionExpression=Key('user_id').eq('update'))
    record = response.get('Items')
    if record == None:
        return None
    return record

def getRssFeed(url):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as res:
        body = res.read().decode('utf-8')
    return body

def putLatestVideo(user_id,video_id,channel_id):
    description = []
    target_url = []
    url = "https://www.youtube.com/feeds/videos.xml?channel_id="+channel_id
    body = getRssFeed(url)
    root = ET.fromstring(body)
    for child in root:
        if child.tag == '{http://www.w3.org/2005/Atom}entry':
            for childchild in child:
                if childchild.tag == '{http://www.w3.org/2005/Atom}title':
                    description.append(child.find('{http://www.w3.org/2005/Atom}title').text)
                if childchild.tag == '{http://www.w3.org/2005/Atom}link':
                    target_url.append(childchild.attrib['href'])
    if not len(description) == len(target_url):
        print(f'Error:::miss match url and description {len(target_url)} : {len(description)} ')
        return
    putVideos(user_id,video_id,target_url,description)

def putVideos(user_id,video_id,video_url,description):
    registVideo(user_id,video_id,video_url[0],description[0])
    registVideoList(user_id,video_id,video_url,description)


def registVideo(user_id,video_id,video_url,description):
    table.put_item(
        Item={
            'user_id': user_id,
            'video_id': video_id,
            'url':video_url,
            'description':description
        }
    )

def registVideoList(user_id,video_id,video_url,description):
    table.put_item(
        Item={
            'user_id': 'list',
            'video_id': f'{user_id}_{video_id}',
            'url':video_url,
            'description':description
        }
    )