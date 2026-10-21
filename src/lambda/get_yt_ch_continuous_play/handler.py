# チャンネル動画の連続再生(登録者のアクセスで次の動画へ進む)
import channelid
import ddbutils
import httputils
import ytutils


def main(event, context):
    print('event:', event)
    channel_id = channelid.from_path(event)
    if channel_id is None:
        return httputils.redirect(httputils.not_found_url())
    ip_address = httputils.headers(event).get('X-Forwarded-For', 'Anonymous').split(',')[0]
    register_id = httputils.query_params(event).get('id', '')
    print('register_id:', register_id)

    # チャンネルが存在するか確認
    record = ddbutils.isExistContinuousChannelID(channel_id, register_id)

    # チャンネルが存在しない場合は新規登録し0番を返却
    if record is None:
        try:
            video_list = ytutils.ytapi_search_channelId(channel_id)
        except Exception as e:
            print(e)
            return httputils.redirect(httputils.not_found_url())
        urls = video_list['videos']['urls']
        if not urls:
            return httputils.redirect(httputils.not_found_url())
        ddbutils.regist_continuous_channel_video_list(video_list, ip_address, ddbutils.ttl_after(hours=3), register_id)
        return httputils.redirect(urls[0])

    urls = record.get('urls') or []
    if not urls:
        return httputils.redirect(httputils.not_found_url())
    # 登録者はカウントアップ
    regist_ip_address = record.get('ip_address')
    print('受信ip_address:', ip_address)
    print('登録ip_address:', regist_ip_address)
    if ip_address == regist_ip_address:
        count = ddbutils.countupContinuousChannelID(channel_id, register_id)
        print(f'count(up): {count}')
    else:
        count = record.get('_count', 0)
        print(f'count(そのまま): {count}')
    # 最後まで再生したら先頭に戻る
    return httputils.redirect(urls[int(count) % len(urls)])
