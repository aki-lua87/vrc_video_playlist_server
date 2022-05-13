import os
import json
import boto3
import ytutils
import ddbutils

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['VRC_VIDEO_TABLE'])


def main(event, context):
    print('event:', event)
    body = json.loads(event['body'])
    channel_id = body.get('channel_id', '')
    # channel_id の スペースを 除去
    channel_id = channel_id.strip()
    print('channel_id:'+channel_id)
    # 引数チェック
    if channel_id == '':
        return {
            'headers': {
                "Access-Control-Allow-Origin": "*"
            },
            'statusCode': 400,
            'body': json.dumps(
                {
                    'error': 'channel_id is not brank'
                }
            )
        }
    # channel_id登録チェック
    isExist, auther = ddbutils.isExistChannelID(channel_id)
    if isExist:
        # 存在する場合登録なしでOKを返却
        return {
            'headers': {
                "Access-Control-Allow-Origin": "*"
            },
            'statusCode': 200,
            'body': json.dumps(
                {
                    'result': 'OK',
                    'auther': auther
                }
            )
        }
    # チャンネル存在チェック & データ取得
    data, isValid = ytutils.getRSS(channel_id)
    if not isValid:
        return {
            'headers': {
                "Access-Control-Allow-Origin": "*"
            },
            'statusCode': 400,
            'body': json.dumps(
                {
                    'result': 'NG',
                    'error': 'channel not exist'
                }
            )
        }
    name, urls, descriptions = ytutils.scrapingRSS(data)

    # レコードを追加
    ddbutils.registChannel(channel_id, name)
    ddbutils.registVideoList(channel_id, urls, descriptions, True, name)
    # https://hoge/videos/yt/{channel_id}

    # OK
    return {
        'headers': {
            "Access-Control-Allow-Origin": "*"
        },
        'statusCode': 200,
        'body': json.dumps({'result': 'OK', 'auther': name}),  # Auther返すこと
    }
