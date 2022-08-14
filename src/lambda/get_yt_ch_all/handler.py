import json
import ytutils


def main(event, context):
    print('event:', event)
    channel_id = event['pathParameters'].get('channel_id')
    channel_id = channel_id.strip()
    httpMethod = event.get('httpMethod')
    print('channel_id:', channel_id)
    print('httpMethod:', httpMethod)
    try:
        # queryStringParameters = event.get('queryStringParameters')
        # count = queryStringParameters.get('n', 20)
        count = 20
    except Exception as e:
        print('[WARN]', e)
        count = 20
    if channel_id is None:
        return {
            'headers': {
                "Access-Control-Allow-Origin": "*"
            },
            'statusCode': 400,
            'body': json.dumps(
                {
                    'result': 'NG',
                    'error': 'bad request [1]'
                }
            )
        }
    b_int = int(count)
    video_list = getVideoList(channel_id, b_int)
    return {
        'headers': {
            "Content-type": "text/html; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
        },
        'statusCode': 200,
        'body': json.dumps(video_list),
    }


def getVideoList(channel_id, n):
    return ytutils.ytapi_search_channelId_ALL(channel_id, n)
