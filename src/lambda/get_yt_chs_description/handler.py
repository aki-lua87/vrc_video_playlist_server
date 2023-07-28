import os
import json
import boto3
from datetime import datetime

import ddbutils
import ytutils

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['VRC_VIDEO_TABLE'])

PC_UA1 = 'Mozilla/5.0'
PC_UA2 = 'NSPlayer'
QUEST_UA = 'stagefright'
PC_AE = 'identity'  # 'Accept-Encoding': 'identity'

# リクエストイメージ
# ?targets=UCxxxxxx,UCyyyyyy

# レスポンスイメージ
# UCxxxxxx:test1,test2,test3,test4,test5\n
# UCyyyyyy:test1,test2,test3,test4


def main(event, context):
    print('event:', event)
    try:
        queryStringParameters = event.get('queryStringParameters')
        targets = queryStringParameters.get('targets', 0)
        targetList = targets.split(',')
        titlesListString = ''
        for target_channel_id in targetList:
            titles = getVideoTitle(target_channel_id)
            titlesString = ','.join(titles)
            titlesListString += f'{target_channel_id}:{titlesString}\n'
        return {
            'headers': {
                "Content-Type": "text/plain; charset=utf-8",
                "Access-Control-Allow-Origin": "*"
            },
            'statusCode': 200,
            'body': titlesListString.rstrip(),
        }
    except Exception as e:
        print(e)
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


def getVideoTitle(channel_id):
    # Videoのlistを取得
    v_list = ddbutils.getVideoList(channel_id)
    if v_list is None:
        return None
    # 更新有無の確認
    latestDateStr = v_list.get('latest_update', 'NoData')
    print('latestDateStr:', latestDateStr)
    now = datetime.now()
    nowstr = now.strftime('%Y%m%d%H')
    if (latestDateStr != nowstr):
        # 更新
        print('update')
        try:
            data = ytutils.ytapi_search_channelId(channel_id)
            ddbutils.registVideoListV2(data, True)
            titles = data['videos']['titles']
        except Exception as e:
            print('[WARN]', e)
            titles = v_list['titles']
    else:
        titles = v_list['titles']
    return titles
