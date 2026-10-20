# チャンネルのライブ配信へリダイレクト
import httputils
import videolist


def main(event, context):
    print('event:', event)
    channel_id = httputils.path_param(event, 'channel_id')
    print('channel_id:', channel_id)
    if channel_id is None:
        return httputils.bad_request('bad request [1]')
    try:
        videos = videolist.channel_videos(channel_id) or {}
    except Exception as e:
        print('[WARN]', e)
        videos = {}
    url = videos.get('live') or httputils.not_found_url()
    print('live:', url)
    return httputils.redirect(url)
