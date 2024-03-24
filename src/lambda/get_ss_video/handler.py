import os
import json
import requests

PC_UA1 = 'Mozilla/5.0'
PC_UA2 = 'NSPlayer'
QUEST_UA = 'stagefright'
PC_AE = 'identity'  # 'Accept-Encoding': 'identity'

cf_domain = os.environ['CF_DOMAIN']
URL_404 = f'{cf_domain}/nf.mp4'


def main(event, context):
    print('event:', event)
    # ssid = event['pathParameters'].get('ssid')

    queryStringParameters = event.get('queryStringParameters')
    httpMethod = event.get('httpMethod')
    ua = event.get('headers').get('User-Agent', '')
    ae = event.get('headers').get('Accept-Encoding', '')
    print('httpMethod:', httpMethod)
    print('User-Agent:', ua)
    print('Accept-Encoding:', ae)
    if queryStringParameters is None:
        return {
            'headers': {
                "Access-Control-Allow-Origin": "*"
            },
            'statusCode': 400,
            'body': json.dumps(
                {
                    'result': 'NG',
                    'error': 'bad request'
                }
            )
        }
    number_srt = queryStringParameters.get('n', 0)
    ssid = queryStringParameters.get('ssid', '')
    ssid = ssid.strip()
    url = f'https://script.google.com/macros/s/{ssid}/exec?mode=url&id={number_srt}'
    title = 'NoData'
    res = requests.get(url)
    responsurl = res.text
    print('responsurl:', responsurl)

    if QUEST_UA in ua:
        # Quest処理 urlを上書き
        print('Quest Request')
        # url = resolvURL(url)
    elif ae == PC_AE:
        # PC処理
        print('PC Request')
    else:
        # Other YTTL JSONを返却
        return {
            'headers': {
                "Content-type": "text/html; charset=utf-8",
                "Access-Control-Allow-Origin": "*",
            },
            'statusCode': 200,
            'body': '{"title":"'+title+'"}',
        }
    return {
        'headers': {
            "Content-type": "text/html; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
            "location": responsurl
        },
        'statusCode': 302,
        'body': "",
    }
