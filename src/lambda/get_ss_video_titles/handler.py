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
    ssid = queryStringParameters.get('ssid', '')
    ssid = ssid.strip()
    url = f'https://script.google.com/macros/s/{ssid}/exec?mode=titles'
    res = requests.get(url)
    responsestring = res.text
    print('responsurl:', responsestring)
    return {
        'headers': {
            "Content-type": "text/plain; charset=utf-8",
            "Access-Control-Allow-Origin": "*"
        },
        'statusCode': 200,
        'body': responsestring,
    }
