# チャンネルのn番目の動画を返却
import httputils
import videolist


def main(event, context):
    print('event:', event)
    channel_id = httputils.path_param(event, 'channel_id')
    params = event.get('queryStringParameters')
    print('channel_id:', channel_id)
    if channel_id is None or params is None:
        return httputils.bad_request()
    n = httputils.parse_index(params.get('n', 0))
    if n is None:
        return httputils.bad_request()
    try:
        videos = videolist.channel_videos(channel_id)
    except Exception as e:
        print('[WARN]', e)
        videos = None
    url, title = videolist.pick(videos, n) or (httputils.not_found_url(), 'Not Found')
    return httputils.video_response(event, url, title)
