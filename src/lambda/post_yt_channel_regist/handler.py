# チャンネル登録
# channel_id には UCxxxx の他に @ハンドル・チャンネルURL・動画URL も指定可
import json

import channelid
import ddbutils
import httputils
import ytutils


def main(event, context):
    print('event:', event)
    try:
        body = json.loads(event.get('body') or '{}')
        value = body.get('channel_id', '')
    except (ValueError, AttributeError):
        value = ''
    # channel_id の スペースを 除去
    value = value.strip() if isinstance(value, str) else ''
    print('channel_id:'+value)
    # 引数チェック
    if value == '':
        return httputils.json_body({'error': 'channel_id is not brank'}, 400)
    channel_id = channelid.resolve(value, allow_url=True)
    print('resolved:', channel_id)
    if channel_id is None:
        return httputils.bad_request('channel not exist')
    # channel_id登録チェック
    isExist, auther = ddbutils.isExistChannelID(channel_id)
    if isExist:
        # 存在する場合登録なしでOKを返却
        return httputils.json_body({'result': 'OK', 'auther': auther, 'channel_id': channel_id})
    # チャンネル存在チェック & データ取得
    try:
        data, isValid = ytutils.getRSS(channel_id)
    except Exception as e:
        # 存在しないチャンネルはRSSが404
        print('[WARN]', e)
        isValid = False
    if not isValid:
        return httputils.bad_request('channel not exist')
    name, urls, descriptions = ytutils.scrapingRSS(data)

    # レコードを追加
    ddbutils.registChannel(channel_id, name)
    ddbutils.registVideoList(channel_id, urls, descriptions, True, name)

    # OK (Autherを返すこと)
    return httputils.json_body({'result': 'OK', 'auther': name, 'channel_id': channel_id})
