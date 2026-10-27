# チャンネルのn番目の動画を返却
import channelid
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
    channel_id = channelid.from_path(event)
    videos = None
    if channel_id is not None:
        try:
            videos = videolist.channel_videos(channel_id, limit=httputils.parse_limit(event))
        except Exception as e:
            print('[WARN]', e)
    url, title = videolist.pick(videos, n) or (httputils.not_found_url(), 'Not Found')
    return httputils.video_response(event, url, title)
