# チャンネル指定(@ハンドル・チャンネルURL・動画URL等)をチャンネルIDに変換 (確認用)
# ?q=https://www.youtube.com/@xxxx
import channelid
import httputils


def main(event, context):
    print('event:', event)
    value = httputils.query_params(event).get('q', '')
    channel_id = channelid.resolve(value, allow_url=True)
    if channel_id is None:
        return httputils.json_text({'result': 'NG', 'error': 'channel not found'}, 404)
    return httputils.json_text({'result': 'OK', 'channel_id': channel_id})
