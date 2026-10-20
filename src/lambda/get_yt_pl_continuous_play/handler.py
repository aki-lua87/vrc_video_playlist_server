# プレイリスト動画の連続再生(登録者のアクセスで次の動画へ進む)
import os
import json
import boto3
import random
import time

import ddbutils
import httputils

regist_lambda_name = os.environ['REGIST_LAMBDA_NAME']


def main(event, context):
    print('event:', event)
    playlist_id = httputils.path_param(event, 'playlist_id')
    print('playlist_id:', playlist_id)
    if playlist_id is None:
        return httputils.bad_request()
    h = httputils.headers(event)
    ae = h.get('Accept-Encoding', '')
    print('User-Agent:', h.get('User-Agent', ''))
    print('Accept-Encoding:', ae)
    ip_address = h.get('X-Forwarded-For', 'Anonymous').split(',')[0]
    register_id = httputils.query_params(event).get('id', '')
    # register_idにrandomが含まれる文字列の場合
    is_random = 'random' in register_id
    is_first = False

    print('register_id:', register_id)
    print('受信ip_address:', ip_address)

    # StringLoader対応
    if httputils.PC_AE != ae:
        time.sleep(1.5)  # YTTL 共通 1.5
        record = ddbutils.is_exist_continuous_playlist_id(playlist_id, register_id)
        if record is None:
            time.sleep(1.5)  # YTTL 予備 1.5
            record = ddbutils.is_exist_continuous_playlist_id(playlist_id, register_id)
            if record is None:
                print('Record None')
                return httputils.redirect(httputils.not_found_url())
        elif ip_address != record.get('ip_address'):
            print('DEBUG 1秒待機前', record)
            time.sleep(1)  # YTTL 非ホスト 1
            record = ddbutils.is_exist_continuous_playlist_id(playlist_id, register_id)
            print('DEBUG 1秒待機後', record)
        titles = record.get('titles') or []
        if not titles:
            return httputils.title_json('Not Found')
        title = titles[current_count(record, is_random) % len(titles)]
        print('StringLoaderでの返却', title, ip_address)
        return httputils.title_json(title)

    # チャンネルが存在するか確認
    record = ddbutils.is_exist_continuous_playlist_id(playlist_id, register_id)

    # チャンネルが存在しない場合は新規登録し0番を返却
    if record is None:
        print('初回登録')
        try:
            is_first = True
            payload = {"register_id": register_id, "playlist_id": playlist_id, "ip_address": ip_address}
            # Lambda関数を呼び出し登録する。同期。
            _ = boto3.client('lambda').invoke(
                FunctionName=regist_lambda_name,
                InvocationType='RequestResponse',  # 同期
                Payload=json.dumps(payload),
            )
            record = ddbutils.is_exist_continuous_playlist_id(playlist_id, register_id)
            if record is None:
                print('Error Record None[初回登録Lambdaエラー]')
                return httputils.redirect(httputils.not_found_url())
        except Exception as e:
            print('regist Error: ', e)
            return httputils.redirect(httputils.not_found_url())

    urls = record.get('urls') or []
    titles = record.get('titles') or []
    if not urls:
        return httputils.redirect(httputils.not_found_url())

    # IPを確認
    isPublishedUser = ip_address == record.get('ip_address')
    print('isPublishedUser:', isPublishedUser)  # 登録者かどうか

    # count値を取得
    if isPublishedUser:
        if is_random:
            count = random.randint(0, len(urls)-1)
            print('count(random):', count)
            ddbutils.update_randcount_continuous_playlist_id(playlist_id, register_id, count)
        elif is_first:
            count = 0
            print('count(first regist):', count)
        else:
            count = int(ddbutils.countup_continuous_playlist_id(playlist_id, register_id))
            print(f'count(up): {count}')
            # 配列越えの時に0に戻す
            if count >= len(urls):
                count = 0
                ddbutils.reset_continuous_playlist_id(playlist_id, register_id)
                print('count(reset): 0')
    else:
        time.sleep(3)  # メイン処理 非ホスト 2
        # 非ホストの場合待機後再度取得
        record = ddbutils.is_exist_continuous_playlist_id(playlist_id, register_id) or record
        count = current_count(record, is_random)
        print('count(そのまま):', count)

    count = count % len(urls)
    print('通常アクセス', titles[count] if count < len(titles) else '', ip_address)
    return httputils.redirect(urls[count])


def current_count(record, is_random):
    key = 'random_count' if is_random else '_count'
    return int(record.get(key) or 0)
