# チャンネル登録
import json

import ddbutils
import httputils
import ytutils


def main(event, context):
    print('event:', event)
    try:
        body = json.loads(event.get('body') or '{}')
        channel_id = body.get('channel_id', '')
    except (ValueError, AttributeError):
        channel_id = ''
    # channel_id の スペースを 除去
    channel_id = channel_id.strip() if isinstance(channel_id, str) else ''
    print('channel_id:'+channel_id)
    # 引数チェック
    if channel_id == '':
        return httputils.json_body({'error': 'channel_id is not brank'}, 400)
    # channel_id登録チェック
    isExist, auther = ddbutils.isExistChannelID(channel_id)
    if isExist:
        # 存在する場合登録なしでOKを返却
        return httputils.json_body({'result': 'OK', 'auther': auther})
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
    return httputils.json_body({'result': 'OK', 'auther': name})
