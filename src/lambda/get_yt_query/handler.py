# 検索結果のn番目の動画を返却
import httputils
import videolist


def main(event, context):
    print('event:', event)
    params = event.get('queryStringParameters')
    if params is None:
        return httputils.bad_request()
    n = httputils.parse_index(params.get('n', 0))
    if n is None:
        return httputils.bad_request()
    query = params.get('q', '')
    try:
        videos = videolist.query_videos(query)
    except Exception as e:
        print('[WARN]', e)
        videos = None
    url, title = videolist.pick(videos, n) or (httputils.not_found_url(), 'Not Found')
    return httputils.video_response(event, url, title)
