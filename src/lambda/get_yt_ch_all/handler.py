# チャンネルの動画リスト(最大21件)をJSONで返却
import json

import channelid
import httputils
import videolist

COUNT = 21


def main(event, context):
    print('event:', event)
    channel_id = channelid.from_path(event)
    if channel_id is None:
        return httputils.json_body({'result': 'NG', 'error': 'channel not found'}, 404)
    try:
        # チャンネル動画のキャッシュを共用
        videos = videolist.channel_videos(channel_id)
    except Exception as e:
        print('[WARN]', e)
        return httputils.json_body({'result': 'NG', 'error': 'YouTube API unavailable'}, 503)
    video_list = {
        'auther': videos.get('auther', ''),
        'videos': [{'title': title, 'url': url}
                   for title, url in zip(videos['titles'][:COUNT], videos['urls'][:COUNT])],
    }
    return {
        'headers': {
            "Content-type": "text/html; charset=utf-8",
            **httputils.CORS,
        },
        'statusCode': 200,
        'body': json.dumps(video_list),
    }
