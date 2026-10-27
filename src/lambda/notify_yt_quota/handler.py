# YouTube Data API の使用量 (概算) を Discord に通知 (1時間ごと)
# 使用量は ytutils が API 呼び出し毎に記録したもの (ddbutils.add_quota_usage)
import datetime
import json
import os

import ddbutils
import notifier

DAILY_QUOTA = 10000
WARN_RATE = 0.8
COLOR = 0xF5A623  # 通常 (オレンジ)
WARN_COLOR = 0xE74C3C  # WARN_RATE 以上 (赤)
UTC = datetime.timezone.utc
JST = datetime.timezone(datetime.timedelta(hours=9))


def main(event, context):
    now = datetime.datetime.now(UTC)
    embed = build_embed(now)
    print(json.dumps(embed, ensure_ascii=False))
    notifier.post_discord({'embeds': [embed]})


def build_embed(now):
    # 直前の1時間 (実行時刻の前の時間帯) と、quotaのリセット (太平洋時間0時) からの累計
    # リセット直後 (直前の1時間が前日分) は前日の最終累計も載せる
    last_hour = now.replace(minute=0, second=0, microsecond=0) - datetime.timedelta(hours=1)
    day_start = pacific_day_start(now)
    after_reset = last_hour < day_start
    start = pacific_day_start(last_hour) if after_reset else day_start
    items = ddbutils.getQuotaUsage(start.strftime(ddbutils.HOURLY), now.strftime(ddbutils.HOURLY))
    hourly = next((item for item in items if item['video_id'] == last_hour.strftime(ddbutils.HOURLY)), {})
    total = sum(int(item.get('total', 0)) for item in items if item['video_id'] >= day_start.strftime(ddbutils.HOURLY))
    rate = total / DAILY_QUOTA
    jst = last_hour.astimezone(JST)
    fields = [{
        'name': f"直近1時間 ({jst:%m/%d %H:00}〜{jst + datetime.timedelta(hours=1):%H:00} JST)",
        'value': f"`{int(hourly.get('total', 0)):,} unit`",
        'inline': False,
    }]
    if after_reset:
        previous = sum(int(item.get('total', 0)) for item in items if item['video_id'] < day_start.strftime(ddbutils.HOURLY))
        fields.insert(0, {
            'name': f"前日の最終累計 ({start.astimezone(JST):%m/%d %H:00} JST〜)",
            'value': f'`{previous:,} / {DAILY_QUOTA:,} unit ({previous / DAILY_QUOTA:.0%})`',
            'inline': False,
        })
    fields += [{'name': key, 'value': f'`{int(value):,}`', 'inline': True}
               for key, value in sorted(hourly.items()) if key not in ('user_id', 'video_id', 'total', 'TTL')]
    return {
        'title': f"{'⚠️' if rate >= WARN_RATE else '📊'} YouTube API 使用量 [{os.environ.get('STAGE', '')}]",
        'description': f'**本日累計: {total:,} / {DAILY_QUOTA:,} unit ({rate:.0%})**',
        'color': WARN_COLOR if rate >= WARN_RATE else COLOR,
        'fields': fields,
        'footer': {'text': f'集計基準: 太平洋時間0時 ({day_start.astimezone(JST):%m/%d %H:00} JST〜) ※概算'},
        'timestamp': now.isoformat(),
    }


def pacific_day_start(now):
    # quotaがリセットされる米国太平洋時間0時 (UTC)
    local = now + pacific_offset(now)
    return local.replace(hour=0, minute=0, second=0, microsecond=0) - pacific_offset(now)


def pacific_offset(utc):
    # 夏時間: 3月第2日曜 2:00 (=10:00 UTC) 〜 11月第1日曜 2:00 (=9:00 UTC)
    def sunday(month, nth):
        first = datetime.datetime(utc.year, month, 1, tzinfo=UTC)
        return first + datetime.timedelta(days=(6 - first.weekday()) % 7 + 7 * (nth - 1))
    dst_start = sunday(3, 2) + datetime.timedelta(hours=10)
    dst_end = sunday(11, 1) + datetime.timedelta(hours=9)
    return datetime.timedelta(hours=-7 if dst_start <= utc < dst_end else -8)
