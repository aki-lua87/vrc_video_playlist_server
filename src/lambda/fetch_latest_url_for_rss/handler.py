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

# root.entry[0].yt:videoId
# https://www.youtube.com/watch?v=

channnel = 'UCoQBJMzcwmXrRSHBFAlTsIw'
user_id = '1e190f4d-a30f-4b5a-80ac-80b524b51be8'
video_id = '13ec6b95-919b-486d-9e23-62bbf622fba6'

def main(event, context):
    discprition = ''
    
    url = "https://www.youtube.com/feeds/videos.xml?channel_id="+channnel
    body = getRssFeed(url)
    root = ET.fromstring(body)
    for child in root:
        if child.tag == '{http://www.w3.org/2005/Atom}entry':
            for childchild in child:
                if childchild.tag == '{http://www.w3.org/2005/Atom}title':
                    discprition = child.find('{http://www.w3.org/2005/Atom}title').text
                    print('discprition:::',discprition)
                if childchild.tag == '{http://www.w3.org/2005/Atom}link':
                    target_url = childchild.attrib['href']
                    print('target_url:::',target_url)
                    break
            break
    putURL(target_url,discprition)


def getRssFeed(url):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as res:
        body = res.read().decode('utf-8')
    return body

def putURL(video_url,discprition):
    table.put_item(
        Item={
            'user_id': user_id,
            'video_id': video_id,
            'url':video_url,
            'discprition':discprition
        }
    )