# プレイリストの動画タイトルリストを返却
from datetime import datetime
import json
import re
from googleapiclient.errors import HttpError
from httplib2 import HttpLib2Error

import ddbutils
import httputils
import ytutils


def main(event, context):
    playlist_id = httputils.path_param(event, 'playlist_id')
    if playlist_id is None or not re.fullmatch(r'[A-Za-z0-9_-]{12,100}', playlist_id):
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
    return httputils.json_text(body, status)


def getVideoURL(playlist_id):
    v_list = ddbutils.getPlaylistVideos(playlist_id)
    if not ddbutils.is_fresh(v_list, ddbutils.DAILY):
        # 更新
        print('update')
        data = ytutils.ytapi_search_playlist(playlist_id)
        ddbutils.registPlaylistVideos(data)
        titles = dict(data['videos'])
        titles['playlist_title'] = data.get('playlist_title', '')
        return titles
    today = datetime.now().strftime(ddbutils.DAILY)
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
