# チャンネル指定を UC形式のチャンネルID に変換
#   UCxxxx / @ハンドル                       : パス・body どちらも可
#   チャンネルURL(/channel/ /@ /user/ /c/) ・動画URL : allow_url=True (regist の body) のみ
# 変換結果は DynamoDB にキャッシュ (見つからなかった結果は短めに保持)
import re
import urllib.error
import urllib.parse

import ddbutils
import httputils
import ytutils

UC_RE = re.compile(r'UC[A-Za-z0-9_-]{22}')
VIDEO_ID_RE = re.compile(r'[A-Za-z0-9_-]{11}')
CACHE_DAYS = 7
NOT_FOUND_CACHE_HOURS = 1
YT_HOSTS = {'youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com'}
VIDEO_PATHS = {'shorts', 'live', 'embed', 'v'}
# youtube.com/xxx の xxx がカスタムURLではないもの
RESERVED_PATHS = {'watch', 'playlist', 'results', 'feed', 'channel', 'user', 'c', 'redirect', 'hashtag'} | VIDEO_PATHS


def from_path(event):
    # パスの {channel_id} (UCxxxx or @ハンドル) を変換
    raw = httputils.path_param(event, 'channel_id')
    channel_id = resolve(raw)
    print('channel_id:', raw, '->', channel_id)
    return channel_id


def resolve(value, allow_url=False):
    # 変換できなければ None
    if not isinstance(value, str):
        return None
    value = urllib.parse.unquote(value).strip()
    if UC_RE.fullmatch(value):
        return value
    target = _parse(value, allow_url)
    if target is None:
        print('unsupported channel:', value)
        return None
    return _lookup(*target)


def _parse(value, allow_url):
    # (種類, 値) を返す。種類: channel / handle / username / custom / video
    if value.startswith('@') and '/' not in value:
        return 'handle', value[1:]
    if not allow_url:
        return None
    url = urllib.parse.urlsplit(value if '://' in value else 'https://' + value)
    host = (url.hostname or '').lower()
    parts = [p for p in url.path.split('/') if p]
    if host == 'youtu.be':
        return ('video', parts[0]) if parts else None
    if host not in YT_HOSTS or not parts:
        return None
    first = parts[0]
    if first.startswith('@'):
        return 'handle', first[1:]
    if first == 'channel' and len(parts) > 1:
        return 'channel', parts[1]
    if first == 'user' and len(parts) > 1:
        return 'username', parts[1]
    if first == 'c' and len(parts) > 1:
        return 'custom', parts[1]
    if first == 'watch':
        video_id = urllib.parse.parse_qs(url.query).get('v', [''])[0]
        return ('video', video_id) if video_id else None
    if first in VIDEO_PATHS and len(parts) > 1:
        return 'video', parts[1]
    if first not in RESERVED_PATHS:
        # 旧形式のカスタムURL youtube.com/xxx
        return 'custom', first
    return None


def _lookup(kind, name):
    if kind == 'channel':
        return name if UC_RE.fullmatch(name) else None
    if kind == 'video' and not VIDEO_ID_RE.fullmatch(name):
        return None
    if not name:
        return None
    # @ハンドル・ユーザー名は大文字小文字を区別しない
    alias = f'{kind}:{name.lower() if kind in ("handle", "username") else name}'
    cached = ddbutils.getChannelAlias(alias)
    if cached is not None:
        print('alias cache:', alias, cached.get('channel_id'))
        return cached.get('channel_id') or None
    try:
        channel_id = _fetch(kind, name)
    except Exception as e:
        # API障害などは結果をキャッシュしない
        print('[WARN] チャンネルID解決失敗', alias, e)
        return None
    print('alias resolved:', alias, channel_id)
    if channel_id and UC_RE.fullmatch(channel_id):
        ddbutils.registChannelAlias(alias, channel_id, ddbutils.ttl_after(days=CACHE_DAYS))
        return channel_id
    ddbutils.registChannelAlias(alias, '', ddbutils.ttl_after(hours=NOT_FOUND_CACHE_HOURS))
    return None


def _fetch(kind, name):
    if kind == 'handle':
        return ytutils.ytapi_channel_id_by_handle(name)
    if kind == 'username':
        return ytutils.ytapi_channel_id_by_username(name)
    if kind == 'video':
        return ytutils.ytapi_channel_id_by_video(name)
    # custom
    try:
        return ytutils.scrape_channel_id(f'https://www.youtube.com/c/{urllib.parse.quote(name)}')
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
