import os
import boto3
from datetime import datetime, timedelta
import ddbutils
import ytutils

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['VRC_VIDEO_TABLE'])


def main(event, context):
    print('event:', event)
    playlist_id = event.get('playlist_id', None)
    register_id = event.get('register_id', None)
    ip_address = event.get('ip_address', 'Anonymous')

    if playlist_id is None or register_id is None:
        return "bad parameter"
    # チャンネルが存在するか確認
    record = ddbutils.is_exist_continuous_playlist_id(playlist_id, register_id)
    if record is not None:
        print('exist record')
        return "exist record"
    try:
        video_list = ytutils.ytapi_search_playlist(playlist_id)
        ddbutils.regist_continuous_playlist_video_list(video_list, ip_address, get_ttl_hours(3), register_id)
    except Exception as e:
        print(e)
        return "error"


def get_ttl_minute(minute):
    start = datetime.now()
    expiration_date = start + timedelta(minutes=minute)
    return round(expiration_date.timestamp())


def get_ttl_hours(hour):
    start = datetime.now()
    expiration_date = start + timedelta(hours=hour)
    return round(expiration_date.timestamp())
