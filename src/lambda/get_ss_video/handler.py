# スプレッドシート(GAS)のn番目の動画を返却
import re
import requests

import httputils


def main(event, context):
    print('event:', event)
    params = event.get('queryStringParameters')
    if params is None:
        return httputils.bad_request()
    ssid = params.get('ssid', '').strip()
    n = httputils.parse_index(params.get('n', 0))
    if not re.fullmatch(r'[A-Za-z0-9_-]+', ssid) or n is None:
        return httputils.bad_request()
    res = requests.get(
        f'https://script.google.com/macros/s/{ssid}/exec',
        params={'mode': 'url', 'id': n},
        timeout=25,
    )
    url = res.text
    print('responsurl:', url)
    return httputils.video_response(event, url, 'NoData')
