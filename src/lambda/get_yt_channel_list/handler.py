# チャンネルの動画タイトルリストを返却
import urllib.request

import channelid
import ddbutils
import httputils
import videolist

# リスト動画作成API (別スタック)
# 動画タイトル一覧を動画化して {CF_DOMAIN}/yt/list/{channel_id}.mp4 に配置する
# VRC上でこの動画を再生するとタイトル一覧を確認できる
CREATE_VIDEO_API = 'https://v9kt9fos4k.execute-api.ap-northeast-1.amazonaws.com/dev/create/video'


def main(event, context):
    print('event:', event)
    channel_id = channelid.from_path(event)
    mode = httputils.query_params(event).get('version', 'v1')
    limit = httputils.parse_limit(event)
    if mode == 'v2':
        # 未登録チャンネルは null
        return httputils.json_text(registered_videos(channel_id, limit))
    if httputils.is_loader(event):
        # StringLoaderからなら文字列を返す
        videos = registered_videos(channel_id, limit) or {}
        return httputils.text(','.join(videos.get('titles', [])))
    return redirect_index_video(channel_id)


def registered_videos(channel_id, limit):
    if channel_id is None:
        return None
    return videolist.channel_videos(channel_id, fetch_if_missing=False, limit=limit)


# タイトル一覧動画(CloudFront)へリダイレクト
def redirect_index_video(channel_id):
    isExist = channel_id is not None and ddbutils.isExistChannelID(channel_id)[0]
    if not isExist:
        print('does not exist', channel_id)
        return httputils.text('video not exist', 404)
    # リスト未作成の場合は下の更新処理で作成する
    record = ddbutils.getVideoList(channel_id) or {}
    isExecIndexCreate = record.get('is_exec_index_create', True)
    print('isExecIndexCreate:', isExecIndexCreate)
    updated = []
    try:
        videolist.channel_videos(channel_id, index_create=False, on_update=lambda: updated.append(True))
        if updated:
            # 更新
            print('update and create')
            call_create_video_api(channel_id)
        elif isExecIndexCreate:
            # 非更新(APIコールのみ)
            print('only create')
            call_create_video_api(channel_id)
            ddbutils.updateChannelIndexCreated(channel_id)
        else:
            print('s3 get')
    except Exception as e:
        print('[WARN] 更新失敗', e)
    return httputils.redirect(f"{httputils.cf_domain()}/yt/list/{channel_id}.mp4")


# リスト動画作成APIをコール
def call_create_video_api(channel_id):
    url = f'{CREATE_VIDEO_API}/{channel_id}'
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req):
        print(f'call {url}')
    print(f'channel_id {channel_id} done')
