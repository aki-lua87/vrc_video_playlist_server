# VRCからコールするためにGET+動画をレスポンス
import os
import boto3
from datetime import datetime
import json
import re
from apiclient.errors import HttpError
from httplib2 import HttpLib2Error

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
    playlist_id = (event.get('pathParameters') or {}).get('playlist_id')
    if not isinstance(playlist_id, str):
        return response(400, {'result': 'NG', 'error': 'invalid playlist ID'})
    playlist_id = playlist_id.strip()
    if not re.fullmatch(r'[A-Za-z0-9_-]{12,100}', playlist_id):
        return response(400, {'result': 'NG', 'error': 'invalid playlist ID'})
    try:
        titles = getVideoURL(playlist_id)
    except HttpError as error:
        status = error.resp.status
        if status in (400, 404):
            return response(status, {'result': 'NG', 'error': 'playlist unavailable'})
        # A 403 can mean either a private playlist or exhausted API quota.
        try:
            details = json.loads(error.content.decode('utf-8'))
            reasons = [item.get('reason') for item in details.get('error', {}).get('errors', [])]
        except (ValueError, UnicodeError, AttributeError):
            reasons = []
        if 'playlistForbidden' in reasons:
            return response(403, {'result': 'NG', 'error': 'playlist unavailable'})
        return response(503, {'result': 'NG', 'error': 'YouTube API unavailable'})
    except (HttpLib2Error, OSError):
        return response(503, {'result': 'NG', 'error': 'YouTube API unavailable'})
    return response(200, titles)


def response(status, body):
    return {
        'headers': {
            "Content-Type": "text/plain; charset=utf-8",
            "Access-Control-Allow-Origin": "*"
        },
        'statusCode': status,
        'body': json.dumps(body, ensure_ascii=False),
    }


def getVideoURL(playlist_id):
    is_update = False
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
        titles = dict(data['videos'])
        titles['playlist_title'] = data.get('playlist_title', '')
    else:
        today = datetime.now().strftime('%Y%m%d')
        if v_list.get('playlist_title_checked') != today:
            # A legacy record can already have today's videos but no list name.
            # Update only metadata; do not refetch pages or change video ordering.
            title = ytutils.ytapi_playlist_title(playlist_id)
            v_list = ddbutils.updatePlaylistTitle(playlist_id, title, today)
        titles = dict(v_list)
        titles['playlist_title'] = v_list.get('playlist_title', '')
        # Keep legacy response fields; this new field is an internal retry marker.
        titles.pop('playlist_title_checked', None)
    return titles
