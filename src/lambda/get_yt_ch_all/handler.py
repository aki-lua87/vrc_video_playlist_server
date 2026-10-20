# チャンネルの動画リスト(最大21件)をJSONで返却
import json

import channelid
import httputils
import ytutils

COUNT = 20


def main(event, context):
    print('event:', event)
    channel_id = channelid.from_path(event)
    if channel_id is None:
        return httputils.json_body({'result': 'NG', 'error': 'channel not found'}, 404)
    video_list = ytutils.ytapi_search_channelId_ALL(channel_id, COUNT)
    return {
        'headers': {
            "Content-type": "text/html; charset=utf-8",
            **httputils.CORS,
        },
        'statusCode': 200,
        'body': json.dumps(video_list),
    }
