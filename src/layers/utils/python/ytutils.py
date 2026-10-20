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
