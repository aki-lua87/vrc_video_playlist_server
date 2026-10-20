# スプレッドシート(GAS)のタイトル一覧を返却
import re
import requests

import httputils


def main(event, context):
    print('event:', event)
    params = event.get('queryStringParameters')
    if params is None:
        return httputils.bad_request()
    ssid = params.get('ssid', '').strip()
    if not re.fullmatch(r'[A-Za-z0-9_-]+', ssid):
        return httputils.bad_request()
    res = requests.get(
        f'https://script.google.com/macros/s/{ssid}/exec',
        params={'mode': 'titles'},
        timeout=25,
    )
    print('response:', res.text)
    return httputils.text(res.text)
