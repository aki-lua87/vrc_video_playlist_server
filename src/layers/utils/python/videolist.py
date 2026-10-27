# 動画リスト取得(DynamoDBキャッシュ + YouTube API更新)
# 返却値は 'titles' / 'urls' を持つdict (limit件まで)
#   キャッシュが有効: DynamoDBレコード
#   更新した場合: APIの取得結果
#   更新に失敗した場合: 古いキャッシュ (キャッシュも無ければ例外)
# limit: 取得件数。キャッシュがそれより少ない件数で取得したものなら更新する
# 更新は next_try で1リクエストに絞る。他のリクエストは更新を待ち (1-2-4秒)、ダメなら古いキャッシュを返す
# 失敗後・フォールバック後の再試行待ちは待たずに古いキャッシュを返す
import datetime
import time

import ddbutils
import ytutils

LOCK_SECONDS = 30  # 更新中 (next_try がこれより先なら再試行待ち)
RETRY_SECONDS = 600  # 取得失敗後に再試行しない時間
WAIT_SECONDS = (1, 2, 4)  # 他のリクエストの更新を待つ間隔
INTERNAL = ('limit', 'next_try')  # 返却しない管理用の属性 (DynamoDBの数値型)
STATS_KIND = {'list_yt_ch': 'channel', 'list_yt_pl': 'playlist', 'list_yt_query': 'search'}


def _load(record, reload, key, fmt, limit, fetch, save, extract, check_limit=True):
    videos, refreshed = _load_videos(record, reload, key, fmt, limit, fetch, save, extract, check_limit)
    # 日次サマリー用のアクセス数 (名前はチャンネル名・プレイリスト名)
    ddbutils.add_access(STATS_KIND[key[0]], key[1], videos.get('auther') or videos.get('playlist_title') or '', refreshed)
    return videos


def _load_videos(record, reload, key, fmt, limit, fetch, save, extract, check_limit):
    # (videos, YouTube APIから再取得したか)
    check = limit if check_limit else None
    if ddbutils.is_fresh(record, fmt, check):
        return _trim(record, limit), False
    if record is not None and not ddbutils.claim_refresh(*key, LOCK_SECONDS):
        return _trim(_wait_refresh(record, reload, fmt, check), limit), False
    print('update')
    try:
        data = fetch()
        save(data)
    except Exception as e:
        if record is None:
            raise
        print('[WARN] 更新失敗のためキャッシュを使用', e)
        ddbutils.delay_refresh(*key, RETRY_SECONDS)
        return _trim(record, limit), True
    return _trim(extract(data), limit), True


def _wait_refresh(record, reload, fmt, limit):
    # 他のリクエストによる更新を待つ。再試行待ちになったら待たない
    for wait in (0, *WAIT_SECONDS):
        if wait:
            time.sleep(wait)
            record = reload() or record
            if ddbutils.is_fresh(record, fmt, limit):
                print('他のリクエストの更新結果を使用')
                return record
        if int(record.get('next_try', 0)) > ddbutils.ttl_after(seconds=LOCK_SECONDS):
            print('再試行待ちのためキャッシュを使用')
            return record
    print('更新待ちタイムアウトのためキャッシュを使用')
    return record


def _trim(videos, limit):
    # 多めにキャッシュされていてもlimit件に揃える
    result = {key: value for key, value in videos.items() if key not in INTERNAL}
    result['titles'] = list(videos.get('titles') or [])[:limit]
    result['urls'] = list(videos.get('urls') or [])[:limit]
    return result


def channel_videos(channel_id, index_create=True, fetch_if_missing=True, limit=ytutils.PAGE_SIZE, on_update=None):
    # 1時間単位で更新。fetch_if_missing=False の場合キャッシュが無ければNone
    # on_update: YouTube APIから取得して保存した後に呼ぶ
    record = ddbutils.getVideoList(channel_id)
    if record is None and not fetch_if_missing:
        return None

    def save(data):
        ddbutils.registVideoListV2(data, index_create)
        if on_update:
            on_update()
    return _load(
        record, lambda: ddbutils.getVideoList(channel_id), ('list_yt_ch', channel_id), ddbutils.HOURLY, limit,
        lambda: ytutils.ytapi_search_channelId(channel_id, limit),
        save,
        lambda data: dict(data['videos'], live=data['live']['url'], auther=data['auther']),
    )


def playlist_videos(playlist_id, limit=ytutils.PAGE_SIZE):
    # 1時間単位で更新
    return _load(
        ddbutils.getPlaylistVideos(playlist_id), lambda: ddbutils.getPlaylistVideos(playlist_id),
        ('list_yt_pl', playlist_id), ddbutils.HOURLY, limit,
        lambda: ytutils.ytapi_search_playlist(playlist_id, limit),
        ddbutils.registPlaylistVideos,
        lambda data: dict(data['videos'], playlist_title=data.get('playlist_title', ''),
                          playlist_title_checked=datetime.datetime.now().strftime(ddbutils.DAILY)),
    )


def query_videos(query):
    # 1日単位で更新。search.list は100 unit/回のため1回(50件)固定
    return _load(
        ddbutils.getQueryVideoList(query), lambda: ddbutils.getQueryVideoList(query),
        ('list_yt_query', query), ddbutils.DAILY, ytutils.PAGE_SIZE,
        lambda: ytutils.ytapi_search_query(query),
        ddbutils.registQueryVideoList,
        lambda data: data['videos'],
        check_limit=False,
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
