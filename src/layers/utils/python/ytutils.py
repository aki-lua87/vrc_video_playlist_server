import html
import re
import urllib.request
import xml.etree.ElementTree as ET
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from httplib2 import HttpLib2Error
import os

import ddbutils

YOUTUBE_URL = 'https://www.youtube.com/watch?v='
ATOM = '{http://www.w3.org/2005/Atom}'
# 1リクエストの最大件数 (playlistItems・videos は1 unit、search は100 unit)
PAGE_SIZE = 50
MAX_PAGES = 10  # 500件
# API別のコスト (unit)。記載の無いものは1
COST = {'search': 100}


def _youtube():
    return build('youtube', 'v3', developerKey=os.environ['API_KEY'])


def _execute(request, api):
    # 使用量を記録して実行 (失敗したリクエストも quota を消費する)
    try:
        return request.execute()
    finally:
        ddbutils.add_quota_usage(api, COST.get(api, 1))


def getRSS(channel_id):
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


def scrapingRSS(rssdata):
    name = rssdata.findtext(f'{ATOM}author/{ATOM}name', '')
    descriptions = []
    urls = []
    for entry in rssdata.iter(f'{ATOM}entry'):
        descriptions.append(entry.findtext(f'{ATOM}title'))
        link = entry.find(f'{ATOM}link')
        if link is not None:
            urls.append(link.attrib['href'])
    return name, urls, descriptions


def _first_item(response):
    items = response.get('items') or []
    return items[0] if items else None


def ytapi_channel_id_by_handle(handle):
    # @ハンドル(@有無どちらも可)からチャンネルID。1 unit
    item = _first_item(_execute(_youtube().channels().list(part='id', forHandle=handle, fields='items(id)'), 'channels'))
    return item and item.get('id')


def ytapi_channel_id_by_username(username):
    # 旧 /user/xxx のユーザー名からチャンネルID。1 unit
    item = _first_item(_execute(_youtube().channels().list(part='id', forUsername=username, fields='items(id)'), 'channels'))
    return item and item.get('id')


def ytapi_channel_id_by_video(video_id):
    # 動画IDから投稿チャンネルのID。1 unit
    item = _first_item(_execute(_youtube().videos().list(part='snippet', id=video_id, fields='items(snippet/channelId)'), 'videos'))
    return item and item.get('snippet', {}).get('channelId')


CANONICAL_RE = re.compile(r'<link rel="canonical" href="https://www\.youtube\.com/channel/(UC[A-Za-z0-9_-]{22})"')


def scrape_channel_id(url):
    # APIで引けない /c/xxx 等はチャンネルページのcanonicalから取得
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'ja'})
    with urllib.request.urlopen(req, timeout=10) as res:
        body = res.read().decode('utf-8', 'replace')
    match = CANONICAL_RE.search(body)
    return match.group(1) if match else None


def ytapi_search_channelId(channelId, limit=PAGE_SIZE):
    video_datas = {
        'channelId': channelId,
        'limit': limit,
        'auther': '',
        'live': {
            'title': '',
            'url': ''
        },
        'videos': {
            'titles': [],
            'urls': [],
        }
    }
    videos, video_datas['fallback'] = _channel_videos(channelId, limit)
    for video_id, snippet in videos:
        url = f'{YOUTUBE_URL}{video_id}'
        video_datas['auther'] = snippet["channelTitle"]
        if snippet["liveBroadcastContent"] == "live":
            video_datas['live']['title'] = snippet["title"]
            video_datas['live']['url'] = url
        elif snippet["liveBroadcastContent"] == "none":
            video_datas['videos']['titles'].append(snippet["title"])
            video_datas['videos']['urls'].append(url)
    return video_datas


def ytapi_search_query(query):
    search_response = _execute(_youtube().search().list(
        q=query,
        part='snippet',
        type='video',
        order='date',
        maxResults=PAGE_SIZE  # 100 unit/ページのため1ページ固定
    ), 'search')

    video_datas = {
        'query': query,
        'videos': {
            'authers': [],
            'titles': [],
            'urls': [],
        }
    }
    for search_result in search_response.get("items", []):
        snippet = _unescape_snippet(search_result["snippet"])
        if snippet["liveBroadcastContent"] == "none":
            video_datas['videos']['titles'].append(snippet["title"])
            video_datas['videos']['urls'].append(f'{YOUTUBE_URL}{search_result["id"]["videoId"]}')
            video_datas['videos']['authers'].append(snippet["channelTitle"])
    return video_datas


# チャンネル動画は (video_id, snippet) の新しい順リストで扱う
# UCxxxx の UC を置き換えた自動生成プレイリスト (非公式)
LONG_VIDEOS = 'UULF'  # 通常動画 (Shorts・配信を除く)
LIVE_VIDEOS = 'UULV'  # 配信 (配信中・アーカイブ)


def _channel_videos(channelId, count):
    # Shortsを除いた最新動画。UULF/UULV が使えなければ検索API (Shortsを含む)
    # (videos, 検索APIにフォールバックしたか)
    try:
        videos = ytapi_channel_recent_videos(channelId, count)
    except HttpError as error:
        print('[WARN] UULF/UULV error:', type(error).__name__)
        videos = None
    if videos is None:
        print('[WARN] UULF/UULV unavailable, fallback to search')
        return _search_channel_videos(channelId, count)[:count], True
    return videos[:count], False


def ytapi_channel_recent_videos(channelId, count):
    # 通常動画と配信を投稿日時順に統合 (playlistItems 1 unit x2 + videos 1 unit)
    # どちらのプレイリストも取得できない場合は None
    if not channelId.startswith('UC'):
        return None
    youtube = _youtube()
    id_lists = [_playlist_video_ids(youtube, prefix + channelId[2:], count)
                for prefix in (LONG_VIDEOS, LIVE_VIDEOS)]
    if all(ids is None for ids in id_lists):
        return None
    ids = list(dict.fromkeys(video_id for ids in id_lists for video_id in ids or []))
    items = []
    for start in range(0, len(ids), 50):
        response = _execute(youtube.videos().list(
            part='snippet',
            id=','.join(ids[start:start + 50]),
            maxResults=50,
            fields='items(id,snippet(title,channelTitle,publishedAt,liveBroadcastContent))'
        ), 'videos')
        items.extend(response.get('items', []))
    items.sort(key=lambda item: item['snippet']['publishedAt'], reverse=True)
    return [(item['id'], item['snippet']) for item in items]


def _playlist_video_ids(youtube, playlist_id, count):
    # 該当する動画が無いチャンネルは404になるため None
    ids = []
    request = youtube.playlistItems().list(
        part='contentDetails',
        playlistId=playlist_id,
        maxResults=min(count, PAGE_SIZE),
        fields='nextPageToken,items/contentDetails/videoId'
    )
    try:
        for _ in range(MAX_PAGES):
            response = _execute(request, 'playlistItems')
            items = response.get('items', [])
            ids.extend(item['contentDetails']['videoId'] for item in items)
            if not items or len(ids) >= count:
                break
            request = youtube.playlistItems().list_next(request, response)
            if request is None:
                break
    except HttpError as error:
        # HttpError's string can contain the request URL (and API key).
        print('playlist unavailable:', playlist_id, type(error).__name__)
        if not ids:
            return None
    return ids[:count]


def _search_channel_videos(channelId, count):
    # 検索APIでの取得 (Shortsを含む)。100 unit/回のため limit に関わらず1回(最大50件)のみ
    search_response = _execute(_youtube().search().list(
        channelId=channelId,
        part='snippet',
        type='video',
        order='date',
        maxResults=min(count, PAGE_SIZE)
    ), 'search')
    return [(search_result["id"]["videoId"], _unescape_snippet(search_result["snippet"]))
            for search_result in search_response.get("items", [])
            if search_result["id"]["kind"] == "youtube#video"]


def _unescape_snippet(snippet):
    # search.list はタイトル等をHTMLエスケープして返す (&amp; &#39; など)
    return dict(snippet, title=html.unescape(snippet['title']),
                channelTitle=html.unescape(snippet['channelTitle']))


def ytapi_playlist_title(pid, youtube=None):
    """Optional display metadata; failure must not discard a usable video list."""
    try:
        if youtube is None:
            youtube = _youtube()
        response = _execute(youtube.playlists().list(
            part='snippet', id=pid, fields='items(id,snippet/title)'
        ), 'playlists')
    except (HttpError, HttpLib2Error, OSError) as error:
        # HttpError's string can contain the request URL (and API key).
        print('Playlist name unavailable:', type(error).__name__)
        return ''
    items = response.get('items', [])
    if not items:
        return ''
    title = items[0].get('snippet', {}).get('title', '')
    return title.strip() if isinstance(title, str) else ''


def ytapi_search_playlist(pid, limit=PAGE_SIZE):
    youtube = _youtube()
    video_datas = {
        'playlistId': pid,
        'limit': limit,
        'videos': {
            'titles': [],
            'urls': []
        }
    }
    titles = video_datas['videos']['titles']
    urls = video_datas['videos']['urls']

    search_request = youtube.playlistItems().list(
        part='snippet',
        playlistId=pid,
        maxResults=PAGE_SIZE,
        fields="nextPageToken,items/snippet/title,items/snippet/resourceId/videoId"
    )
    for page in range(MAX_PAGES):
        print('page:', page)
        search_response = _execute(search_request, 'playlistItems')
        for search_result in search_response.get("items", []):
            titles.append(search_result["snippet"]["title"])
            urls.append(f'{YOUTUBE_URL}{search_result["snippet"]["resourceId"]["videoId"]}')
        if len(urls) >= limit:
            break
        search_request = youtube.playlistItems().list_next(search_request, search_response)
        if search_request is None:
            break
    del titles[limit:], urls[limit:]
    # Reuse the client and fetch once per list refresh, not once per page/video.
    video_datas['playlist_title'] = ytapi_playlist_title(pid, youtube)
    return video_datas
