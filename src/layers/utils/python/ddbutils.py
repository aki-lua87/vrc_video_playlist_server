import os
import boto3
import datetime

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['VRC_VIDEO_TABLE'])

# latest_update の更新単位
HOURLY = '%Y%m%d%H'
DAILY = '%Y%m%d'

continuous_yt_playlist_id = 'continuous_yt_playlist_id'


def is_fresh(record, fmt=HOURLY):
    # 現在の更新単位内に更新済みか
    if record is None:
        return False
    latest = record.get('latest_update', 'NoData')
    print('latestDateStr:', latest)
    return latest == datetime.datetime.now().strftime(fmt)


def ttl_after(**delta):
    # 例: ttl_after(hours=3)
    return round((datetime.datetime.now() + datetime.timedelta(**delta)).timestamp())


def _get(user_id, video_id):
    response = table.get_item(
        Key={
            'user_id': user_id,
            'video_id': f'{video_id}',
        }
    )
    return response.get('Item')


def _count_up(user_id, video_id) -> int:
    response = table.update_item(
        Key={
            'user_id': user_id,
            'video_id': video_id,
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


# チャンネル指定(@ハンドル等) -> チャンネルID のキャッシュ
# channel_id が '' のものは見つからなかった結果
def getChannelAlias(alias):
    record = _get('yt_channel_alias', alias)
    if record is None or int(record.get('TTL', 0)) <= datetime.datetime.now().timestamp():
        # TTL切れ(DynamoDBの削除は遅延する)
        return None
    return record


def registChannelAlias(alias, channel_id, ttl):
    table.put_item(
        Item={
            'user_id': 'yt_channel_alias',
            'video_id': alias,
            'channel_id': channel_id,
            'TTL': ttl
        }
    )


# チャンネルが登録済みか確認
def isExistChannelID(channel_id):
    record = _get('yt_channnel_id', channel_id)
    if record is None:
        return False, ""
    return True, record.get('author')


# チャンネルIDに紐づくリストを取得
def getVideoList(channel_id):
    return _get('list_yt_ch', channel_id)


# プレイリストIDに紐づくリストを取得
def getPlaylistVideos(playlist_id):
    return _get('list_yt_pl', playlist_id)


def getQueryVideoList(q):
    return _get('list_yt_query', q)


def registQueryVideoList(video_datas):
    now = datetime.datetime.now()
    table.put_item(
        Item={
            'user_id': 'list_yt_query',
            'video_id': video_datas['query'],
            'titles': video_datas['videos']['titles'],
            'urls': video_datas['videos']['urls'],
            'latest_update': now.strftime(HOURLY),
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
            'latest_update': now.strftime(HOURLY),
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
            'latest_update': now.strftime(HOURLY),
        }
    )


# 動画作成済みフラグ
def updateChannelIndexCreated(channel_id):
    table.update_item(
        Key={
            'user_id': 'list_yt_ch',
            'video_id': channel_id
        },
        UpdateExpression="set is_exec_index_create=:ieic",
        ExpressionAttributeValues={
            ':ieic': False,
        },
        ReturnValues="UPDATED_NEW"
    )


def registPlaylistVideos(video_datas):
    now = datetime.datetime.now()
    table.put_item(
        Item={
            'user_id': 'list_yt_pl',
            'video_id': video_datas['playlistId'],
            'titles': video_datas['videos']['titles'],
            'urls': video_datas['videos']['urls'],
            'latest_update': now.strftime(DAILY),  # 1日単位で更新
            'playlist_title': video_datas.get('playlist_title', ''),
            # Record attempts too, so an optional metadata failure is not retried
            # on every /titles request. Failed lookups replace stale names with ''.
            'playlist_title_checked': now.strftime(DAILY),
        }
    )


def updatePlaylistTitle(playlist_id, title, checked_date):
    """Backfill legacy records without replacing their video list/update date."""
    response = table.update_item(
        Key={'user_id': 'list_yt_pl', 'video_id': playlist_id},
        UpdateExpression='SET #title = :title, #checked = :checked',
        ExpressionAttributeNames={
            '#title': 'playlist_title', '#checked': 'playlist_title_checked'
        },
        ExpressionAttributeValues={':title': title, ':checked': checked_date},
        ConditionExpression='attribute_exists(user_id) AND attribute_exists(video_id)',
        ReturnValues='ALL_NEW'
    )
    return response['Attributes']


# 連続再生チャンネルが登録済みか確認、存在する場合はデータを返却
def isExistContinuousChannelID(channel_id, id=''):
    return _get('continuous_yt_channnel_id', f'{channel_id}_{id}')


def countupContinuousChannelID(channel_id, id='') -> int:
    return _count_up('continuous_yt_channnel_id', f'{channel_id}_{id}')


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
            'latest_update': now.strftime(HOURLY),
            'TTL': ttl
        }
    )


def regist_continuous_playlist_video_list(video_datas, ip_address, ttl, id='', random_count=0):
    now = datetime.datetime.now()
    table.put_item(
        Item={
            'user_id': continuous_yt_playlist_id,
            'video_id': video_datas['playlistId'] + '_' + id,
            'titles': video_datas['videos']['titles'],
            'urls': video_datas['videos']['urls'],
            '_count': 0,
            'ip_address': ip_address,
            'latest_update': now.strftime(DAILY),
            'random_count': random_count,
            'TTL': ttl
        }
    )


def countup_continuous_playlist_id(playlist_id, id='') -> int:
    return _count_up(continuous_yt_playlist_id, f'{playlist_id}_{id}')


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
    return _get(continuous_yt_playlist_id, f'{playlist_id}_{id}')
