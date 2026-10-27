# Discord Webhook への通知
import json
import os
import urllib.request


def post_discord(payload):
    url = os.environ.get('DISCORD_WEBHOOK_URL')
    if not url:
        print('DISCORD_WEBHOOK_URL 未設定のため通知しない')
        return
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        # DiscordはUser-Agentの無いリクエストを拒否する
        headers={'Content-Type': 'application/json', 'User-Agent': 'vrc-video-api-notifier/1.0'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=10) as res:
        print('discord:', res.status)
