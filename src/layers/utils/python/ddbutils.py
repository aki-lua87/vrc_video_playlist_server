import os
import boto3
import datetime
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['VRC_VIDEO_TABLE'])


# チャンネルが登録済みか確認
def isExistChannelID(channel_id):
    response = table.get_item(
        Key={
            'user_id': 'yt_channnel_id',
            'video_id': channel_id
        }
    )
    isExistRecord = response.get('Item')
    if isExistRecord is None:
        return False, ""
    return True, isExistRecord.get('author')


# チャンネルIDに紐づくリストを取得
def getVideoList(channel_id):
    response = table.get_item(
        Key={
            'user_id': 'list_yt_ch',
            'video_id': f'{channel_id}',
        }
    )
    record = response.get('Item')
    if record is None:
        return None
    return record


# プレイリストIDに紐づくリストを取得
def getPlaylistVideos(playlist_id):
    response = table.get_item(
        Key={
            'user_id': 'list_yt_pl',
            'video_id': f'{playlist_id}',
        }
    )
    record = response.get('Item')
    if record is None:
        return None
    return record


def getQueryVideoList(q):
    response = table.get_item(
        Key={
            'user_id': 'list_yt_query',
            'video_id': f'{q}',
        }
    )
    record = response.get('Item')
    if record is None:
        return None
    return record


def registQueryVideoList(video_datas):
    now = datetime.datetime.now()
    table.put_item(
        Item={
            'user_id': 'list_yt_query',
            'video_id': video_datas['query'],
            'titles': video_datas['videos']['titles'],
            'urls': video_datas['videos']['urls'],
            'latest_update': now.strftime('%Y%m%d%H'),
        }
    )


# 登録情報更新
def registChannel(channel_id, author):
    table.put_item(
        Item={
            'user_id': 'yt_channnel_id',
            'video_id': channel_id,
            'author': author
        }
    )


# List更新
def registVideoList(channel_id, video_urls, descriptions, index_create, auther=''):
    now = datetime.datetime.now()
    table.put_item(
        Item={
            'user_id': 'list_yt_ch',
            'video_id': f'{channel_id}',
            'auther': auther,
            'live': '',
            'titles': descriptions,
            'urls': video_urls,
            'is_exec_index_create': index_create,
            'latest_update': now.strftime('%Y%m%d%H'),
        }
    )


# List更新ver.api
def registVideoListV2(video_datas, index_create):
    now = datetime.datetime.now()
    table.put_item(
        Item={
            'user_id': 'list_yt_ch',
            'video_id': video_datas['channelId'],
            'auther': video_datas['auther'],
            'titles': video_datas['videos']['titles'],
            'urls': video_datas['videos']['urls'],
            'live': video_datas['live']['url'],
            'is_exec_index_create': index_create,
            'latest_update': now.strftime('%Y%m%d%H'),
        }
    )


def registPlaylistVideos(video_datas):
    now = datetime.datetime.now()
    table.put_item(
        Item={
            'user_id': 'list_yt_pl',
            'video_id': video_datas['playlistId'],
            'titles': video_datas['videos']['titles'],
            'urls': video_datas['videos']['urls'],
            'latest_update': now.strftime('%Y%m%d'),  # 1日単位で更新
        }
    )


# チャンネルIDに紐づくリストを取得
def getTVer(attribute):
    response = table.get_item(
        Key={
            'user_id': 'tver',
            'video_id': f'{attribute}',
        }
    )
    record = response.get('Item')
    if record is None:
        return None
    return record


# attributeから番組名で取得
def getTVer2(attribute, title):
    response = table.query(
        KeyConditionExpression=Key('user_id').eq(
            f'tver_{attribute}') & Key('video_id').begins_with(title)
    )
    record = response.get('Items')
    if record is None:
        return None
    return record


def getQuestURL(url):
    response = table.get_item(
        Key={
            'user_id': 'quest_url',
            'video_id': f'{url}',
        }
    )
    record = response.get('Item')
    if record is None:
        return None
    return record.get('quest_url')


# URLをキーにURLを登録(TTL付き)
def registQuestURL(yt_url, quest_url, ttl):
    table.put_item(
        Item={
            'user_id': 'quest_url',
            'video_id': yt_url,
            'quest_url': quest_url,
            'TTL': ttl
        }
    )


# 連続再生チャンネルが登録済みか確認、存在する場合はデータを返却
def isExistContinuousChannelID(channel_id, id=''):
    response = table.get_item(
        Key={
            'user_id': 'continuous_yt_channnel_id',
            'video_id': f'{channel_id}_{id}',
        }
    )
    record = response.get('Item')
    if record is None:
        return None
    return record


def countupContinuousChannelID(channel_id, id='') -> int:
    response = table.update_item(
        Key={
            'user_id': 'continuous_yt_channnel_id',
            'video_id': f'{channel_id}_{id}',
        },
        UpdateExpression="ADD #name :increment",
        ExpressionAttributeNames={
            '#name': '_count'
        },
        ExpressionAttributeValues={
            ":increment": 1
        },
        ReturnValues="UPDATED_NEW"
    )
    return response.get('Attributes').get('_count')


def regist_continuous_channel_video_list(video_datas, ip_address, ttl, id=''):
    now = datetime.datetime.now()
    table.put_item(
        Item={
            'user_id': 'continuous_yt_channnel_id',
            'video_id': video_datas['channelId'] + '_' + id,
            'auther': video_datas['auther'],
            'titles': video_datas['videos']['titles'],
            'urls': video_datas['videos']['urls'],
            '_count': 0,
            'ip_address': ip_address,
            'latest_update': now.strftime('%Y%m%d%H'),
            'TTL': ttl
        }
    )


continuous_yt_playlist_id = 'continuous_yt_playlist_id'


def regist_continuous_playlist_video_list(video_datas, ip_address, ttl, id='', random_count=0):
    now = datetime.datetime.now()
    table.put_item(
        Item={
            'user_id': continuous_yt_playlist_id,
            'video_id': video_datas['playlistId'] + '_' + id,
            # 'authers': video_datas['videos']['authers'],
            'titles': video_datas['videos']['titles'],
            'urls': video_datas['videos']['urls'],
            '_count': 0,
            'ip_address': ip_address,
            'latest_update': now.strftime('%Y%m%d'),
            'random_count': random_count,
            'TTL': ttl
        }
    )


def countup_continuous_playlist_id(playlist_id, id='') -> int:
    response = table.update_item(
        Key={
            'user_id': continuous_yt_playlist_id,
            'video_id': f'{playlist_id}_{id}',
        },
        UpdateExpression="ADD #name :increment",
        ExpressionAttributeNames={
            '#name': '_count'
        },
        ExpressionAttributeValues={
            ":increment": 1
        },
        ReturnValues="UPDATED_NEW"
    )
    return response.get('Attributes').get('_count')


def reset_continuous_playlist_id(playlist_id, id=''):
    response = table.update_item(
        Key={
            'user_id': continuous_yt_playlist_id,
            'video_id': f'{playlist_id}_{id}',
        },
        UpdateExpression="set #name=:new_count",
        ExpressionAttributeNames={
            '#name': '_count'
        },
        ExpressionAttributeValues={
            ":new_count": 0
        },
        ReturnValues="UPDATED_NEW"
    )
    return response.get('Attributes').get('_count')


def update_randcount_continuous_playlist_id(playlist_id, id='', random_count=0):
    response = table.update_item(
        Key={
            'user_id': continuous_yt_playlist_id,
            'video_id': f'{playlist_id}_{id}',
        },
        UpdateExpression="set random_count=:new_count",
        ExpressionAttributeValues={
            ":new_count": random_count
        },
        ReturnValues="UPDATED_NEW"
    )
    return response.get('Attributes').get('random_count')


def is_exist_continuous_playlist_id(playlist_id, id=''):
    response = table.get_item(
        Key={
            'user_id': continuous_yt_playlist_id,
            'video_id': f'{playlist_id}_{id}',
        }
    )
    record = response.get('Item')
    if record is None:
        return None
    return record
