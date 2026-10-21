import re
import urllib.request
import xml.etree.ElementTree as ET
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from httplib2 import HttpLib2Error
import os

YOUTUBE_URL = 'https://www.youtube.com/watch?v='
ATOM = '{http://www.w3.org/2005/Atom}'


def _youtube():
    return build('youtube', 'v3', developerKey=os.environ['API_KEY'])


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
    item = _first_item(_youtube().channels().list(part='id', forHandle=handle, fields='items(id)').execute())
    return item and item.get('id')


def ytapi_channel_id_by_username(username):
    # 旧 /user/xxx のユーザー名からチャンネルID。1 unit
    item = _first_item(_youtube().channels().list(part='id', forUsername=username, fields='items(id)').execute())
    return item and item.get('id')


def ytapi_channel_id_by_video(video_id):
    # 動画IDから投稿チャンネルのID。1 unit
    item = _first_item(_youtube().videos().list(part='snippet', id=video_id, fields='items(snippet/channelId)').execute())
    return item and item.get('snippet', {}).get('channelId')


CANONICAL_RE = re.compile(r'<link rel="canonical" href="https://www\.youtube\.com/channel/(UC[A-Za-z0-9_-]{22})"')


def scrape_channel_id(url):
    # APIで引けない /c/xxx 等はチャンネルページのcanonicalから取得
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'ja'})
    with urllib.request.urlopen(req, timeout=10) as res:
        body = res.read().decode('utf-8', 'replace')
    match = CANONICAL_RE.search(body)
    return match.group(1) if match else None


def ytapi_search_channelId(channelId):
    search_response = _youtube().search().list(
        channelId=channelId,
        part='snippet',
        type='video',
        order='date',
        maxResults=21
    ).execute()

    video_datas = {
        'channelId': channelId,
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
    for search_result in search_response.get("items", []):
        if search_result["id"]["kind"] != "youtube#video":
            continue
        snippet = search_result["snippet"]
        url = f'{YOUTUBE_URL}{search_result["id"]["videoId"]}'
        video_datas['auther'] = snippet["channelTitle"]
        if snippet["liveBroadcastContent"] == "live":
            video_datas['live']['title'] = snippet["title"]
            video_datas['live']['url'] = url
        elif snippet["liveBroadcastContent"] == "none":
            video_datas['videos']['titles'].append(snippet["title"])
            video_datas['videos']['urls'].append(url)
    return video_datas


def ytapi_search_query(query):
    search_response = _youtube().search().list(
        q=query,
        part='snippet',
        type='video',
        order='date',
        maxResults=21
    ).execute()

    video_datas = {
        'query': query,
        'videos': {
            'authers': [],
            'titles': [],
            'urls': [],
        }
    }
    for search_result in search_response.get("items", []):
        snippet = search_result["snippet"]
        if snippet["liveBroadcastContent"] == "none":
            video_datas['videos']['titles'].append(snippet["title"])
            video_datas['videos']['urls'].append(f'{YOUTUBE_URL}{search_result["id"]["videoId"]}')
            video_datas['videos']['authers'].append(snippet["channelTitle"])
    return video_datas


def ytapi_search_channelId_ALL(channelId, n=19):
    # 再起させても MAX 500 らしい・・・
    youtube = _youtube()
    nextPagetoken = None
    video_datas = {
        'auther': '',
        'videos': []
    }
    for _ in range(20):
        search_response = youtube.search().list(
            channelId=channelId,
            part='snippet',
            type='video',
            order='date',
            maxResults=50,
            pageToken=nextPagetoken
        ).execute()

        for search_result in search_response.get("items", []):
            if search_result["id"]["kind"] != "youtube#video":
                continue
            snippet = search_result["snippet"]
            video_datas['auther'] = snippet["channelTitle"]
            if snippet["liveBroadcastContent"] == "none":
                video_datas['videos'].append({
                    'title': snippet["title"],
                    'url': f'{YOUTUBE_URL}{search_result["id"]["videoId"]}'
                })
                if len(video_datas['videos']) > n:
                    print(len(video_datas['videos']))
                    return video_datas
        nextPagetoken = search_response.get("nextPageToken")
        if nextPagetoken is None:
            break
    print(len(video_datas['videos']))
    return video_datas


def ytapi_playlist_title(pid, youtube=None):
    """Optional display metadata; failure must not discard a usable video list."""
    try:
        if youtube is None:
            youtube = _youtube()
        response = youtube.playlists().list(
            part='snippet', id=pid, fields='items(id,snippet/title)'
        ).execute()
    except (HttpError, HttpLib2Error, OSError) as error:
        # HttpError's string can contain the request URL (and API key).
        print('Playlist name unavailable:', type(error).__name__)
        return ''
    items = response.get('items', [])
    if not items:
        return ''
    title = items[0].get('snippet', {}).get('title', '')
    return title.strip() if isinstance(title, str) else ''


def ytapi_search_playlist(pid):
    youtube = _youtube()
    video_datas = {
        'playlistId': pid,
        'videos': {
            'titles': [],
            'urls': []
        }
    }
    max_loop = 10

    search_request = youtube.playlistItems().list(
        part='snippet',
        playlistId=pid,
        maxResults=50,
        fields="nextPageToken,items/snippet/title,items/snippet/resourceId/videoId"
    )
    while search_request is not None:
        print('loop_count:', max_loop)
        max_loop = max_loop - 1
        if max_loop <= 0:
            break
        search_response = search_request.execute()
        for search_result in search_response.get("items", []):
            title = search_result["snippet"]["title"]
            url = f'{YOUTUBE_URL}{search_result["snippet"]["resourceId"]["videoId"]}'
            video_datas['videos']['titles'].append(title)
            video_datas['videos']['urls'].append(url)
        search_request = youtube.playlistItems().list_next(search_request, search_response)
    # Reuse the client and fetch once per list refresh, not once per page/video.
    video_datas['playlist_title'] = ytapi_playlist_title(pid, youtube)
    return video_datas
