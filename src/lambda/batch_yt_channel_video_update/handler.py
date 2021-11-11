import os
import urllib.request
import boto3
from boto3.dynamodb.conditions import Key
import xml.etree.ElementTree as ET

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['VRC_VIDEO_TABLE'])


def main(event, context):
    videosInfo = getUpadteChannelList()
    if videosInfo is None:
        print('[ERROR] not data')
        return
    for videoInfo in videosInfo:
        try:
            channel_id = videoInfo['video_id']
            data = getData(channel_id)
            descriptions = []
            urls = []
            for child in data:
                if child.tag == '{http://www.w3.org/2005/Atom}author':
                    for author in child:
                        if author.tag == '{http://www.w3.org/2005/Atom}name':
                            name = child.find(
                                '{http://www.w3.org/2005/Atom}name').text
                if child.tag == '{http://www.w3.org/2005/Atom}entry':
                    for childchild in child:
                        if childchild.tag == '{http://www.w3.org/2005/Atom}title':
                            descriptions.append(child.find(
                                '{http://www.w3.org/2005/Atom}title').text)
                        if childchild.tag == '{http://www.w3.org/2005/Atom}link':
                            urls.append(childchild.attrib['href'])
            print('[INFO] ', 'regist ', channel_id)
            registVideoList(channel_id, urls, descriptions)
            # 一覧更新フラグを立てる
            updateChannelUpdateSuccess(channel_id, name)
        except Exception as e:
            print('[ERROR]', videoInfo, e)


def getUpadteChannelList():
    response = table.query(KeyConditionExpression=Key(
        'user_id').eq('yt_channnel_id'))
    record = response.get('Items')
    if record is None:
        return None
    return record


def getRssFeed(url):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as res:
        body = res.read().decode('utf-8')
    return body


def getData(channel_id):
    url = "https://www.youtube.com/feeds/videos.xml?channel_id="+channel_id
    body = getRssFeed(url)
    root = ET.fromstring(body)
    if len(root) == 0:
        return []
    return root


def registVideoList(channel_id, video_urls, descriptions):
    table.put_item(
        Item={
            'user_id': 'list_yt_ch',
            'video_id': f'{channel_id}',
            'titles': descriptions,
            'urls': video_urls
        }
    )


def updateChannelUpdateSuccess(channel_id, name):
    table.put_item(
        Item={
            'user_id': 'yt_channnel_id',
            'video_id': channel_id,
            'author': name,
            'index_create': True
        }
    )
