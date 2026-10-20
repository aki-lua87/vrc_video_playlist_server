# 複数チャンネルの動画タイトルリストを返却
import httputils
import videolist

# リクエストイメージ
# ?targets=UCxxxxxx,UCyyyyyy

# レスポンスイメージ
# UCxxxxxx:test1,test2,test3,test4,test5\n
# UCyyyyyy:test1,test2,test3,test4


def main(event, context):
    print('event:', event)
    targets = httputils.query_params(event).get('targets')
    if not targets:
        return httputils.bad_request()
    lines = []
    for channel_id in targets.split(','):
        try:
            # 未登録チャンネルはタイトル無し
            videos = videolist.channel_videos(channel_id, fetch_if_missing=False) or {}
        except Exception as e:
            print('[WARN]', channel_id, e)
            videos = {}
        lines.append(f"{channel_id}:{','.join(videos.get('titles', []))}")
    return httputils.text('\n'.join(lines))
