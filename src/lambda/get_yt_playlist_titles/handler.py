# VRCからコールするためにGET+動画をレスポンス
import os
import boto3
from datetime import datetime

import ddbutils
import ytutils

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['VRC_VIDEO_TABLE'])

PC_UA1 = 'Mozilla/5.0'
PC_UA2 = 'NSPlayer'
QUEST_UA = 'stagefright'
PC_AE = 'identity'  # 'Accept-Encoding': 'identity'
LOADER_UA = 'UnityPlayer'  # stringLoaderはこれ？


def main(event, context):
    print('event:', event)
    httpMethod = event.get('httpMethod')
    ua = event.get('headers').get('User-Agent', '')
    print('httpMethod:', httpMethod)
    print('User-Agent:', ua)
    playlist_id = event['pathParameters'].get('playlist_id')
    playlist_id = playlist_id.strip()
    print('channel_id:', playlist_id)
    titles = getVideoURL(playlist_id)
    print('titles:', titles)
    return {
        'headers': {
            "Content-Type": "text/plain; charset=utf-8",
            "Access-Control-Allow-Origin": "*"
        },
        'statusCode': 200,
        'body': ','.join(titles),
    }


def getVideoURL(playlist_id):
    is_update = False
    titles = []
    # Videoのlistを取得
    v_list = ddbutils.getPlaylistVideos(playlist_id)
    if v_list is None:
        print('v_list is None')
        is_update = True
    else:
        # 更新有無の確認
        latestDateStr = v_list.get('latest_update', 'NoData')
        print('latestDateStr:', latestDateStr)
        now = datetime.now()
        nowstr = now.strftime('%Y%m%d')
        if (latestDateStr != nowstr):
            print('latestDateStr != nowstr')
            is_update = True
    if is_update:
        # 更新
        print('update')
        data = ytutils.ytapi_search_playlist(playlist_id)
        ddbutils.registPlaylistVideos(data)
        titles = data['videos']['titles']
    else:
        titles = v_list['titles']
    return titles
