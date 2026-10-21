# 複数チャンネルの動画タイトルリストを返却
import channelid
import httputils
import videolist

# リクエストイメージ
# ?targets=UCxxxxxx,@handle

# レスポンスイメージ
# UCxxxxxx:test1,test2,test3,test4,test5\n
# UCyyyyyy:test1,test2,test3,test4


def main(event, context):
    print('event:', event)
    targets = httputils.query_params(event).get('targets')
    if not targets:
        return httputils.bad_request()
    lines = []
    for target in targets.split(','):
        # 行のキーはリクエストされた文字列のまま返す
        channel_id = channelid.resolve(target)
        videos = {}
        if channel_id is not None:
            try:
                # 未登録チャンネルはタイトル無し
                videos = videolist.channel_videos(channel_id, fetch_if_missing=False) or {}
            except Exception as e:
                print('[WARN]', channel_id, e)
        lines.append(f"{target}:{','.join(videos.get('titles', []))}")
    return httputils.text('\n'.join(lines))
