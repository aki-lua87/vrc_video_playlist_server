# 前日 (JST) のアクセス上位のチャンネル・プレイリスト・検索を Discord に通知 (毎日9:00 JST)
# アクセス数は videolist が記録したもの (ddbutils.add_access)
import datetime
import json
import os

import ddbutils
import notifier

TOP = 10
KINDS = (('channel', '📺 チャンネル'), ('playlist', '📃 プレイリスト'), ('search', '🔍 検索'))
COLOR = 0x3498DB
NAME_LENGTH = 40
UTC = datetime.timezone.utc


def main(event, context):
    day = datetime.datetime.now(ddbutils.JST).date() - datetime.timedelta(days=1)
    embed = build_embed(day)
    print(json.dumps(embed, ensure_ascii=False))
    notifier.post_discord({'embeds': [embed]})


def build_embed(day):
    items = ddbutils.getAccessStats(day.strftime(ddbutils.DAILY))
    fields = []
    for kind, label in KINDS:
        rows = sorted((item for item in items if item.get('kind') == kind),
                      key=lambda item: int(item.get('count', 0)), reverse=True)
        count = sum(int(item.get('count', 0)) for item in rows)
        lines = [f"{rank}. {_name(item)} `{int(item.get('count', 0)):,}回`"
                 + (f" (更新{int(item['refresh'])})" if item.get('refresh') else '')
                 for rank, item in enumerate(rows[:TOP], 1)]
        fields.append({
            'name': f'{label} ({len(rows):,}件 / {count:,}回)',
            'value': '\n'.join(lines) or 'なし',
            'inline': False,
        })
    return {
        'title': f"📈 アクセスサマリー [{os.environ.get('STAGE', '')}] {day:%Y/%m/%d}",
        'description': (f"**アクセス {sum(int(item.get('count', 0)) for item in items):,}回**"
                        f" / YouTube API {quota_usage(day):,} unit (概算)"),
        'color': COLOR,
        'fields': fields,
        'footer': {'text': '集計: JST 0:00〜24:00 / (更新n) はYouTube APIでの再取得回数'},
    }


def quota_usage(day):
    # JSTの1日分 (UTCの時間別記録を合算)
    start = datetime.datetime.combine(day, datetime.time(), ddbutils.JST).astimezone(UTC)
    end = start + datetime.timedelta(hours=23)
    items = ddbutils.getQuotaUsage(start.strftime(ddbutils.HOURLY), end.strftime(ddbutils.HOURLY))
    return sum(int(item.get('total', 0)) for item in items)


def _name(item):
    # 名前が無ければID・検索語。Discordの書式記号はエスケープ
    name = item.get('name') or item.get('target', '')
    if len(name) > NAME_LENGTH:
        name = name[:NAME_LENGTH] + '…'
    for char in '\\*_`~|>':
        name = name.replace(char, '\\' + char)
    return name
