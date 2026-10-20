# チャンネルのライブ配信へリダイレクト
import channelid
import httputils
import videolist


def main(event, context):
    print('event:', event)
    channel_id = channelid.from_path(event)
    videos = {}
    if channel_id is not None:
        try:
            videos = videolist.channel_videos(channel_id) or {}
        except Exception as e:
            print('[WARN]', e)
    url = videos.get('live') or httputils.not_found_url()
    print('live:', url)
    return httputils.redirect(url)
