# プレイリスト連続再生の初回登録 (get_yt_pl_continuous_play から同期呼び出し)
import ddbutils
import ytutils


def main(event, context):
    print('event:', event)
    playlist_id = event.get('playlist_id', None)
    register_id = event.get('register_id', None)
    ip_address = event.get('ip_address', 'Anonymous')

    if playlist_id is None or register_id is None:
        return "bad parameter"
    # チャンネルが存在するか確認
    record = ddbutils.is_exist_continuous_playlist_id(playlist_id, register_id)
    if record is not None:
        print('exist record')
        return "exist record"
    try:
        video_list = ytutils.ytapi_search_playlist(playlist_id)
        ddbutils.regist_continuous_playlist_video_list(video_list, ip_address, ddbutils.ttl_after(hours=6), register_id)
    except Exception as e:
        print(e)
        return "error"
