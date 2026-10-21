# 動画リスト取得(DynamoDBキャッシュ + YouTube API更新)
# 返却値は 'titles' / 'urls' を持つdict
#   キャッシュが有効: DynamoDBレコード
#   更新した場合: APIの取得結果
#   更新に失敗した場合: 古いキャッシュ (キャッシュも無ければ例外)
import ddbutils
import ytutils


def _load(record, fmt, fetch, save, extract):
    if ddbutils.is_fresh(record, fmt):
        return record
    print('update')
    try:
        data = fetch()
        save(data)
    except Exception as e:
        if record is None:
            raise
        print('[WARN] 更新失敗のためキャッシュを使用', e)
        return record
    return extract(data)


def channel_videos(channel_id, index_create=True, fetch_if_missing=True):
    # 1時間単位で更新。fetch_if_missing=False の場合キャッシュが無ければNone
    record = ddbutils.getVideoList(channel_id)
    if record is None and not fetch_if_missing:
        return None
    return _load(
        record, ddbutils.HOURLY,
        lambda: ytutils.ytapi_search_channelId(channel_id),
        lambda data: ddbutils.registVideoListV2(data, index_create),
        lambda data: dict(data['videos'], live=data['live']['url']),
    )


def playlist_videos(playlist_id):
    # 1日単位で更新
    return _load(
        ddbutils.getPlaylistVideos(playlist_id), ddbutils.DAILY,
        lambda: ytutils.ytapi_search_playlist(playlist_id),
        ddbutils.registPlaylistVideos,
        lambda data: data['videos'],
    )


def query_videos(query):
    # 1時間単位で更新
    return _load(
        ddbutils.getQueryVideoList(query), ddbutils.HOURLY,
        lambda: ytutils.ytapi_search_query(query),
        ddbutils.registQueryVideoList,
        lambda data: data['videos'],
    )


def pick(videos, n):
    # n番目の (url, title)。範囲外ならNone
    if videos is None or n is None:
        return None
    urls = videos.get('urls') or []
    titles = videos.get('titles') or []
    if n >= len(urls):
        print('out of range:', n, len(urls))
        return None
    title = titles[n] if n < len(titles) else ''
    print(title)
    return urls[n], title
