# プレイリストのn番目の動画を返却
import httputils
import videolist


def main(event, context):
    print('event:', event)
    playlist_id = httputils.path_param(event, 'playlist_id')
    params = event.get('queryStringParameters')
    print('playlist_id:', playlist_id)
    if playlist_id is None or params is None:
        return httputils.bad_request()
    n = httputils.parse_index(params.get('n', 0))
    if n is None:
        return httputils.bad_request()
    url, title = getVideoURL(playlist_id, n, httputils.parse_limit(event))
    return httputils.video_response(event, url, title)


def getVideoURL(playlist_id, n, limit=httputils.LIMIT_STEP):
    try:
        videos = videolist.playlist_videos(playlist_id, limit)
    except Exception as e:
        print('[WARN]', e)
        videos = None
    return videolist.pick(videos, n) or (httputils.not_found_url(), 'Not Found')
