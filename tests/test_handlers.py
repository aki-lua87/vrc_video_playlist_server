"""Offline tests for shared helpers and handlers. No AWS/YouTube access needed."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
LAYER = 'src/layers/utils/python'
CF = 'https://example.invalid'
UC = 'UCXcjvt8cOfwtcqaMeE7-hqA'
UC2 = 'UC_x5XG1OV2P6uZZ5FSM9Ttw'
NF = f'{CF}/nf.mp4'
QUEST = {'User-Agent': 'stagefright/1.2', 'Accept-Encoding': ''}
PC = {'User-Agent': 'Mozilla/5.0', 'Accept-Encoding': 'identity'}
OTHER = {'User-Agent': 'UnityPlayer/6000', 'Accept-Encoding': 'gzip'}


def module(name, **attributes):
    result = types.ModuleType(name)
    result.__dict__.update(attributes)
    return result


def load(name, relative_path):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def event(path=None, query=None, headers=None, body=None):
    return {'pathParameters': path, 'queryStringParameters': query, 'headers': headers or {}, 'body': body}


def videos(n):
    return {'titles': [f't{i}' for i in range(n)], 'urls': [f'https://youtu.be/{i}' for i in range(n)]}


class OfflineTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table = MagicMock()
        boto = module('boto3', resource=MagicMock(), client=MagicMock())
        boto.resource.return_value.Table.return_value = cls.table
        stubs = {
            'boto3': boto,
            'googleapiclient': module('googleapiclient'),
            'googleapiclient.discovery': module('googleapiclient.discovery', build=MagicMock()),
            'googleapiclient.errors': module('googleapiclient.errors', HttpError=type('HttpError', (Exception,), {})),
            'httplib2': module('httplib2', HttpLib2Error=type('HttpLib2Error', (Exception,), {})),
            'requests': module('requests', get=MagicMock()),
        }
        env = {'VRC_VIDEO_TABLE': 'offline-table', 'API_KEY': 'offline-only', 'CF_DOMAIN': CF,
               'REGIST_LAMBDA_NAME': 'offline-regist'}
        with patch.dict(sys.modules, stubs), patch.dict(os.environ, env):
            cls.ddb = load('t_ddbutils', f'{LAYER}/ddbutils.py')
            with patch.dict(sys.modules, {'ddbutils': cls.ddb}):
                cls.yt = load('t_ytutils', f'{LAYER}/ytutils.py')
            cls.http = load('t_httputils', f'{LAYER}/httputils.py')
            cls.notifier = load('t_notifier', f'{LAYER}/notifier.py')
            layer = {'ddbutils': cls.ddb, 'ytutils': cls.yt, 'httputils': cls.http, 'notifier': cls.notifier}
            with patch.dict(sys.modules, layer):
                cls.vl = load('t_videolist', f'{LAYER}/videolist.py')
                cls.ch = load('t_channelid', f'{LAYER}/channelid.py')
            cls.handlers = {}
            with patch.dict(sys.modules, dict(layer, videolist=cls.vl, channelid=cls.ch)):
                for path in sorted((ROOT / 'src/lambda').glob('*/handler.py')):
                    name = path.parent.name
                    cls.handlers[name] = load(f't_{name}', path.relative_to(ROOT))
        cls.requests = stubs['requests']

    def setUp(self):
        env = patch.dict(os.environ, {'CF_DOMAIN': CF, 'API_KEY': 'offline-only'})
        env.start()
        self.addCleanup(env.stop)
        out = contextlib.redirect_stdout(io.StringIO())
        out.__enter__()
        self.addCleanup(out.__exit__, None, None, None)
        self.table.reset_mock(return_value=True, side_effect=True)


class HttpUtilsTests(OfflineTestCase):
    def test_all_handlers_import(self):
        self.assertEqual(len(self.handlers), 18)

    def test_parse_index(self):
        for value, expected in (('3', 3), (0, 0), ('-1', None), ('abc', None), (None, None)):
            with self.subTest(value=value):
                self.assertEqual(self.http.parse_index(value), expected)

    def test_path_param_trims_and_rejects_non_string(self):
        self.assertEqual(self.http.path_param({'pathParameters': {'id': ' UCx '}}, 'id'), 'UCx')
        self.assertIsNone(self.http.path_param({'pathParameters': {'id': '  '}}, 'id'))
        self.assertIsNone(self.http.path_param({'pathParameters': None}, 'id'))

    def test_players_are_redirected_and_others_get_title(self):
        for headers in (QUEST, PC):
            with self.subTest(headers=headers):
                result = self.http.video_response(event(headers=headers), 'https://youtu.be/x', 't')
                self.assertEqual((result['statusCode'], result['headers']['location']), (302, 'https://youtu.be/x'))
        result = self.http.video_response(event(headers=OTHER), 'https://youtu.be/x', 't')
        self.assertEqual(result['statusCode'], 200)

    def test_parse_limit_rounds_up_to_50_and_clamps(self):
        for value, expected in ((None, 50), ('abc', 50), ('0', 50), ('-100', 50), ('1', 50), ('50', 50),
                                ('51', 100), ('120', 150), ('500', 500), ('501', 500), ('10000', 500)):
            with self.subTest(value=value):
                query = None if value is None else {'limit': value}
                self.assertEqual(self.http.parse_limit(event(query=query)), expected)

    def test_title_json_escapes_quotes(self):
        title = '激辛 "ブルダック" \\ test'
        body = self.http.title_json(title)['body']
        self.assertEqual(json.loads(body), {'title': title})


class VideoListTests(OfflineTestCase):
    def now(self):
        return self.ddb.datetime.datetime.now().strftime(self.ddb.HOURLY)

    def test_fresh_cache_does_not_call_api(self):
        record = dict(videos(2), latest_update=self.now(), limit=50)
        with patch.object(self.ddb, 'getVideoList', return_value=record), \
                patch.object(self.yt, 'ytapi_search_channelId') as api:
            self.assertEqual(self.vl.channel_videos(UC), dict(videos(2), latest_update=self.now()))
        api.assert_not_called()

    def test_cache_fetched_with_smaller_limit_is_refreshed(self):
        # limit の無い旧レコードも更新対象
        for record in (dict(videos(2), latest_update=self.now(), limit=50), dict(videos(2), latest_update=self.now())):
            data = {'channelId': UC, 'limit': 100, 'auther': 'a', 'live': {'url': ''}, 'videos': videos(80)}
            with self.subTest(record=record), patch.object(self.ddb, 'getVideoList', return_value=record), \
                    patch.object(self.yt, 'ytapi_search_channelId', return_value=data) as api, \
                    patch.object(self.ddb, 'registVideoListV2'):
                self.assertEqual(len(self.vl.channel_videos(UC, limit=100)['urls']), 80)
            api.assert_called_once_with(UC, 100)

    def test_larger_cache_is_trimmed_to_limit(self):
        record = dict(videos(300), latest_update=self.now(), limit=500)
        with patch.object(self.ddb, 'getVideoList', return_value=record), \
                patch.object(self.yt, 'ytapi_search_channelId') as api:
            result = self.vl.channel_videos(UC)
        api.assert_not_called()
        self.assertEqual(result['urls'], videos(50)['urls'])
        self.assertNotIn('limit', result)
        self.assertIsNone(self.vl.pick(result, 50))

    def test_query_cache_is_daily_and_not_refetched_for_limit(self):
        record = dict(videos(60), latest_update=self.ddb.datetime.datetime.now().strftime(self.ddb.DAILY))
        with patch.object(self.ddb, 'getQueryVideoList', return_value=record), \
                patch.object(self.yt, 'ytapi_search_query') as api:
            self.assertEqual(len(self.vl.query_videos('q')['urls']), 50)
        api.assert_not_called()

    def test_stale_cache_is_used_when_api_fails(self):
        record = dict(videos(2), latest_update='2000010100')
        with patch.object(self.ddb, 'getVideoList', return_value=record), \
                patch.object(self.yt, 'ytapi_search_channelId', side_effect=OSError('down')):
            self.assertEqual(self.vl.channel_videos(UC), record)

    def test_missing_cache_and_api_failure_raises(self):
        with patch.object(self.ddb, 'getQueryVideoList', return_value=None), \
                patch.object(self.yt, 'ytapi_search_query', side_effect=OSError('down')), \
                self.assertRaises(OSError):
            self.vl.query_videos('q')

    def test_unregistered_channel_is_not_fetched_when_disabled(self):
        with patch.object(self.ddb, 'getVideoList', return_value=None), \
                patch.object(self.yt, 'ytapi_search_channelId') as api:
            self.assertIsNone(self.vl.channel_videos(UC, fetch_if_missing=False))
        api.assert_not_called()

    def test_refresh_returns_api_videos_with_live(self):
        data = {'channelId': UC, 'auther': 'a', 'live': {'title': 'L', 'url': 'https://youtu.be/live'}, 'videos': videos(1)}
        with patch.object(self.ddb, 'getVideoList', return_value=None), \
                patch.object(self.yt, 'ytapi_search_channelId', return_value=data), \
                patch.object(self.ddb, 'registVideoListV2') as save:
            result = self.vl.channel_videos(UC, index_create=False)
        save.assert_called_once_with(data, False)
        self.assertEqual(result, dict(videos(1), live='https://youtu.be/live', auther='a'))

    def test_other_requests_wait_for_refresh_result(self):
        stale = dict(videos(2), latest_update='2000010100', limit=50)
        fresh = dict(videos(3), latest_update=self.now(), limit=50)
        with patch.object(self.ddb, 'getVideoList', side_effect=[stale, stale, fresh]), \
                patch.object(self.ddb, 'claim_refresh', return_value=False) as claim, \
                patch.object(self.vl.time, 'sleep') as sleep, \
                patch.object(self.yt, 'ytapi_search_channelId') as api:
            self.assertEqual(self.vl.channel_videos(UC)['urls'], videos(3)['urls'])
        claim.assert_called_once_with('list_yt_ch', UC, self.vl.LOCK_SECONDS)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [1, 2])
        api.assert_not_called()

    def test_wait_gives_up_after_three_retries(self):
        stale = dict(videos(2), latest_update='2000010100', limit=50)
        with patch.object(self.ddb, 'getVideoList', return_value=stale), \
                patch.object(self.ddb, 'claim_refresh', return_value=False), \
                patch.object(self.vl.time, 'sleep') as sleep:
            self.assertEqual(self.vl.channel_videos(UC)['urls'], videos(2)['urls'])
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [1, 2, 4])

    def test_retry_backoff_does_not_wait(self):
        # 失敗後・フォールバック後 (next_try が30秒より先) は待っても更新されない
        backoff = dict(videos(2), latest_update='2000010100', limit=50, next_try=self.ddb.ttl_after(minutes=10))
        locked = dict(backoff, next_try=self.ddb.ttl_after(seconds=20))
        # 最初から再試行待ち → 待たない / 更新中 → 1回待ったら再試行待ち(更新失敗)になった
        for records, sleeps in (([backoff], 0), ([locked, backoff], 1)):
            with self.subTest(sleeps=sleeps), \
                    patch.object(self.ddb, 'getVideoList', side_effect=records), \
                    patch.object(self.ddb, 'claim_refresh', return_value=False), \
                    patch.object(self.vl.time, 'sleep') as sleep:
                self.vl.channel_videos(UC)
            self.assertEqual(sleep.call_count, sleeps)

    def test_failed_refresh_delays_retry(self):
        record = dict(videos(2), latest_update='2000010100', limit=50)
        with patch.object(self.ddb, 'getPlaylistVideos', return_value=record), \
                patch.object(self.ddb, 'claim_refresh', return_value=True), \
                patch.object(self.ddb, 'delay_refresh') as delay, \
                patch.object(self.yt, 'ytapi_search_playlist', side_effect=OSError('quota')):
            self.assertEqual(self.vl.playlist_videos('PLx')['urls'], videos(2)['urls'])
        delay.assert_called_once_with('list_yt_pl', 'PLx', self.vl.RETRY_SECONDS)

    def test_missing_cache_is_fetched_without_claim(self):
        data = {'channelId': UC, 'auther': 'a', 'live': {'url': ''}, 'videos': videos(1)}
        with patch.object(self.ddb, 'getVideoList', return_value=None), \
                patch.object(self.ddb, 'claim_refresh') as claim, \
                patch.object(self.yt, 'ytapi_search_channelId', return_value=data), \
                patch.object(self.ddb, 'registVideoListV2'):
            self.vl.channel_videos(UC)
        claim.assert_not_called()

    def test_claim_condition_and_conflict(self):
        self.assertTrue(self.ddb.claim_refresh('list_yt_ch', UC, 30))
        args = self.table.update_item.call_args.kwargs
        self.assertIn('next_try < :now', args['ConditionExpression'])
        self.assertAlmostEqual(args['ExpressionAttributeValues'][':until'], self.ddb.ttl_after(seconds=30), delta=5)
        conflict = Exception('conditional')
        conflict.response = {'Error': {'Code': 'ConditionalCheckFailedException'}}
        self.table.update_item.side_effect = conflict
        self.assertFalse(self.ddb.claim_refresh('list_yt_ch', UC, 30))
        # DynamoDB側の障害では取得を止めない
        self.table.update_item.side_effect = OSError('ddb down')
        self.assertTrue(self.ddb.claim_refresh('list_yt_ch', UC, 30))

    def test_fallback_result_is_not_refetched_for_a_day(self):
        data = {'channelId': UC, 'auther': 'a', 'live': {'url': ''}, 'videos': videos(1), 'fallback': True}
        self.ddb.registVideoListV2(data, False)
        item = self.table.put_item.call_args.kwargs['Item']
        self.assertAlmostEqual(item['next_try'], self.ddb.ttl_after(days=1), delta=5)
        self.ddb.registVideoListV2(dict(data, fallback=False), False)
        self.assertNotIn('next_try', self.table.put_item.call_args.kwargs['Item'])

    def test_internal_numbers_are_not_returned(self):
        record = dict(videos(1), latest_update='2000010100', limit=50, next_try=self.ddb.ttl_after(days=1))
        with patch.object(self.ddb, 'getVideoList', return_value=record), \
                patch.object(self.ddb, 'claim_refresh', return_value=False):
            result = self.vl.channel_videos(UC)
        self.assertFalse({'limit', 'next_try'} & result.keys())

    def test_pick(self):
        self.assertEqual(self.vl.pick(videos(2), 1), ('https://youtu.be/1', 't1'))
        self.assertIsNone(self.vl.pick(videos(2), 2))
        self.assertIsNone(self.vl.pick(None, 0))


def snippet(title, published, live='none'):
    return {'title': title, 'channelTitle': 'ch', 'publishedAt': published, 'liveBroadcastContent': live}


class ChannelVideoFetchTests(OfflineTestCase):
    def youtube(self, playlists, details):
        # playlists: プレイリストID → 動画ID一覧 (None は404)
        youtube = MagicMock()

        def playlist_items(playlistId, **kwargs):
            request = MagicMock()
            ids = playlists.get(playlistId)
            if ids is None:
                request.execute.side_effect = self.yt.HttpError('404')
            else:
                request.execute.return_value = {'items': [{'contentDetails': {'videoId': i}} for i in ids]}
            return request

        def video_details(id, **kwargs):
            request = MagicMock()
            request.execute.return_value = {'items': [{'id': i, 'snippet': details[i]} for i in id.split(',') if i in details]}
            return request

        youtube.playlistItems.return_value.list.side_effect = playlist_items
        youtube.videos.return_value.list.side_effect = video_details
        return youtube

    def test_long_videos_and_lives_are_merged_without_shorts(self):
        youtube = self.youtube({'UULF' + UC[2:]: ['v1', 'v3'], 'UULV' + UC[2:]: ['now', 'up', 'v2']}, {
            'v1': snippet('動画1', '2026-10-03T00:00:00Z'),
            'v2': snippet('アーカイブ', '2026-10-02T00:00:00Z'),
            'v3': snippet('動画3', '2026-10-01T00:00:00Z'),
            'now': snippet('配信中', '2026-09-01T00:00:00Z', 'live'),
            'up': snippet('予約', '2026-10-05T00:00:00Z', 'upcoming'),
        })
        with patch.object(self.yt, '_youtube', return_value=youtube):
            data = self.yt.ytapi_search_channelId(UC)
        self.assertEqual(data['videos']['titles'], ['動画1', 'アーカイブ', '動画3'])
        self.assertEqual(data['live']['url'], 'https://www.youtube.com/watch?v=now')
        youtube.search.assert_not_called()

    def test_channel_without_lives_uses_long_videos_only(self):
        youtube = self.youtube({'UULF' + UC[2:]: ['v1']}, {'v1': snippet('動画1', '2026-10-03T00:00:00Z')})
        with patch.object(self.yt, '_youtube', return_value=youtube):
            data = self.yt.ytapi_search_channelId(UC)
        self.assertEqual((data['auther'], data['videos']['titles'], data['fallback']), ('ch', ['動画1'], False))
        youtube.search.assert_not_called()

    def test_long_video_pages_are_followed_up_to_limit(self):
        ids = [f'v{i:03}' for i in range(120)]
        pages = [ids[:50], ids[50:100], ids[100:]]
        youtube = self.youtube({'UULF' + UC[2:]: pages[0]},
                               {i: snippet(i, f'2026-01-01T00:00:{999 - k:03}Z') for k, i in enumerate(ids)})
        uulf_next = [MagicMock(), MagicMock()]
        for request, page in zip(uulf_next, pages[1:]):
            request.execute.return_value = {'items': [{'contentDetails': {'videoId': i}} for i in page]}
        youtube.playlistItems.return_value.list_next.side_effect = uulf_next
        with patch.object(self.yt, '_youtube', return_value=youtube):
            data = self.yt.ytapi_search_channelId(UC, 100)
        self.assertEqual(data['limit'], 100)
        self.assertEqual(data['videos']['titles'], ids[:100])
        # 50件ずつ: UULF 2ページ (100件で打ち切り) + videos.list 2回
        self.assertEqual(youtube.playlistItems.return_value.list_next.call_count, 1)
        self.assertEqual(youtube.videos.return_value.list.call_count, 2)

    def test_search_query_is_one_page_of_50(self):
        youtube = MagicMock()
        youtube.search.return_value.list.return_value.execute.return_value = {'items': []}
        with patch.object(self.yt, '_youtube', return_value=youtube):
            self.yt.ytapi_search_query('q')
        self.assertEqual(youtube.search.return_value.list.call_args.kwargs['maxResults'], 50)

    def test_falls_back_to_search_when_playlists_unavailable(self):
        youtube = self.youtube({}, {})
        youtube.search.return_value.list.return_value.execute.return_value = {'items': [
            {'id': {'kind': 'youtube#video', 'videoId': 's1'}, 'snippet': snippet('A&amp;B &#39;x&#39;', '2026-10-03T00:00:00Z')},
        ]}
        with patch.object(self.yt, '_youtube', return_value=youtube):
            data = self.yt.ytapi_search_channelId(UC)
            query = self.yt.ytapi_search_query('q')
        self.assertEqual(data['videos']['urls'], ['https://www.youtube.com/watch?v=s1'])
        # search.list のHTMLエスケープは戻す
        self.assertEqual(data['videos']['titles'], ["A&B 'x'"])
        self.assertEqual(query['videos']['titles'], ["A&B 'x'"])

    def test_search_fallback_is_one_call_of_50_even_with_large_limit(self):
        youtube = self.youtube({}, {})
        youtube.search.return_value.list.return_value.execute.return_value = {'items': []}
        with patch.object(self.yt, '_youtube', return_value=youtube):
            self.yt.ytapi_search_channelId(UC, 500)
        youtube.search.return_value.list.assert_called_once()
        self.assertEqual(youtube.search.return_value.list.call_args.kwargs['maxResults'], 50)


class VideoHandlerTests(OfflineTestCase):
    def test_out_of_range_index_redirects_to_not_found(self):
        h = self.handlers['get_yt_channel']
        with patch.object(self.vl, 'channel_videos', return_value=videos(2)):
            result = h.main(event({'channel_id': UC}, {'n': '5'}, PC), None)
        self.assertEqual(result['headers']['location'], NF)

    def test_api_failure_without_cache_redirects_to_not_found(self):
        for name, target in (('get_yt_channel', 'channel_videos'), ('get_yt_playlist', 'playlist_videos'),
                             ('get_yt_query', 'query_videos')):
            with self.subTest(name=name), patch.object(self.vl, target, side_effect=OSError('down')):
                path = {'channel_id': UC, 'playlist_id': 'PLx'}
                result = self.handlers[name].main(event(path, {'n': '0', 'q': 'x'}, QUEST), None)
                self.assertEqual(result['headers']['location'], NF)

    def test_invalid_index_is_bad_request(self):
        for n in ('abc', '-1'):
            with self.subTest(n=n):
                result = self.handlers['get_yt_channel'].main(event({'channel_id': UC}, {'n': n}, PC), None)
                self.assertEqual(result['statusCode'], 400)

    def test_limit_parameter_is_passed_to_video_list(self):
        with patch.object(self.vl, 'channel_videos', return_value=videos(200)) as load_videos:
            result = self.handlers['get_yt_channel'].main(event({'channel_id': UC}, {'n': '149', 'limit': '120'}, PC), None)
        load_videos.assert_called_once_with(UC, limit=150)
        self.assertEqual(result['headers']['location'], 'https://youtu.be/149')
        with patch.object(self.vl, 'playlist_videos', return_value=videos(3)) as load_videos:
            self.handlers['get_yt_playlist'].main(event({'playlist_id': 'PLx'}, {'n': '0', 'limit': '500'}, PC), None)
        load_videos.assert_called_once_with('PLx', 500)

    def test_quest_gets_same_redirect_as_pc(self):
        with patch.object(self.vl, 'playlist_videos', return_value=videos(3)):
            for headers in (QUEST, PC):
                result = self.handlers['get_yt_playlist'].main(event({'playlist_id': 'PLx'}, {'n': '2'}, headers), None)
                self.assertEqual(result['headers']['location'], 'https://youtu.be/2')

    def test_ss_video_rejects_invalid_id(self):
        result = self.handlers['get_ss_video'].main(event(query={'ssid': '../x', 'n': '0'}, headers=PC), None)
        self.assertEqual(result['statusCode'], 400)
        self.requests.get.assert_not_called()


class ListHandlerTests(OfflineTestCase):
    def test_channel_titles_unregistered_is_404(self):
        h = self.handlers['get_yt_channel_list']
        with patch.object(self.ddb, 'isExistChannelID', return_value=(False, '')):
            result = h.main(event({'channel_id': UC}, None, {'User-Agent': 'curl'}), None)
        self.assertEqual(result['statusCode'], 404)

    def test_channel_titles_registered_without_list_does_not_crash(self):
        h = self.handlers['get_yt_channel_list']
        with patch.object(self.ddb, 'isExistChannelID', return_value=(True, 'a')), \
                patch.object(self.ddb, 'getVideoList', return_value=None), \
                patch.object(self.yt, 'ytapi_search_channelId', side_effect=OSError('down')):
            result = h.main(event({'channel_id': UC}, None, {'User-Agent': 'curl'}), None)
        self.assertEqual(result['statusCode'], 302)
        self.assertEqual(result['headers']['location'], f'{CF}/yt/list/{UC}.mp4')

    def test_channel_titles_v2_and_loader_for_unregistered(self):
        h = self.handlers['get_yt_channel_list']
        with patch.object(self.ddb, 'getVideoList', return_value=None):
            self.assertEqual(h.main(event({'channel_id': UC}, {'version': 'v2'}), None)['body'], 'null')
            self.assertEqual(h.main(event({'channel_id': UC}, None, OTHER), None)['body'], '')

    def test_chs_description_skips_unregistered_channel(self):
        h = self.handlers['get_yt_chs_description']
        with patch.object(self.vl, 'channel_videos', return_value=videos(2)), \
                patch.object(self.ch, 'resolve', side_effect=[UC, None]):
            result = h.main(event(query={'targets': f'{UC},@nobody'}), None)
        self.assertEqual(result['body'], f'{UC}:t0,t1\n@nobody:')

    def test_ch_all_uses_channel_cache(self):
        h = self.handlers['get_yt_ch_all']
        with patch.object(self.vl, 'channel_videos', return_value=dict(videos(30), auther='ch')) as load_videos:
            result = h.main(event({'channel_id': UC}), None)
        load_videos.assert_called_once_with(UC)
        body = json.loads(result['body'])
        self.assertEqual(body['auther'], 'ch')
        self.assertEqual(len(body['videos']), 21)
        self.assertEqual(body['videos'][0], {'title': 't0', 'url': 'https://youtu.be/0'})
        with patch.object(self.vl, 'channel_videos', side_effect=OSError('down')):
            self.assertEqual(h.main(event({'channel_id': UC}), None)['statusCode'], 503)

    def test_channel_titles_creates_index_video_only_after_refresh(self):
        h = self.handlers['get_yt_channel_list']

        def refreshed(channel_id, **kwargs):
            kwargs['on_update']()
        for side_effect, flag, created, marked in ((refreshed, False, True, False), (None, True, True, True), (None, False, False, False)):
            with self.subTest(refresh=bool(side_effect), flag=flag), \
                    patch.object(self.ddb, 'isExistChannelID', return_value=(True, 'a')), \
                    patch.object(self.ddb, 'getVideoList', return_value={'is_exec_index_create': flag}), \
                    patch.object(self.vl, 'channel_videos', side_effect=side_effect), \
                    patch.object(h, 'call_create_video_api') as create, \
                    patch.object(self.ddb, 'updateChannelIndexCreated') as mark:
                h.main(event({'channel_id': UC}, None, {'User-Agent': 'curl'}), None)
            self.assertEqual((create.called, mark.called), (created, marked))

    def test_live_redirect(self):
        h = self.handlers['get_ytlive_channel']
        with patch.object(self.vl, 'channel_videos', return_value={'live': 'https://youtu.be/live'}):
            self.assertEqual(h.main(event({'channel_id': UC}), None)['headers']['location'], 'https://youtu.be/live')
        with patch.object(self.vl, 'channel_videos', return_value={'live': ''}):
            self.assertEqual(h.main(event({'channel_id': UC}), None)['headers']['location'], NF)


class ContinuousAndRegistTests(OfflineTestCase):
    def test_channel_continuous_wraps_after_last_video(self):
        h = self.handlers['get_yt_ch_continuous_play']
        record = dict(videos(3), ip_address='1.1.1.1', _count=2)
        with patch.object(self.ddb, 'isExistContinuousChannelID', return_value=record), \
                patch.object(self.ddb, 'countupContinuousChannelID', return_value=3):
            result = h.main(event({'channel_id': UC}, None, dict(PC, **{'X-Forwarded-For': '1.1.1.1, 2.2.2.2'})), None)
        self.assertEqual(result['headers']['location'], 'https://youtu.be/0')

    def test_channel_continuous_empty_channel_is_not_found(self):
        h = self.handlers['get_yt_ch_continuous_play']
        data = {'channelId': UC, 'auther': '', 'live': {'url': ''}, 'videos': videos(0)}
        with patch.object(self.ddb, 'isExistContinuousChannelID', return_value=None), \
                patch.object(self.yt, 'ytapi_search_channelId', return_value=data), \
                patch.object(self.ddb, 'regist_continuous_channel_video_list') as save:
            result = h.main(event({'channel_id': UC}, None, PC), None)
        self.assertEqual(result['headers']['location'], NF)
        save.assert_not_called()

    def test_playlist_continuous_loader_title_is_valid_json(self):
        h = self.handlers['get_yt_pl_continuous_play']
        record = {'titles': ['a "quoted" title'], 'urls': ['u'], 'ip_address': '1.1.1.1', '_count': 0}
        with patch.object(self.ddb, 'is_exist_continuous_playlist_id', return_value=record), \
                patch.object(h.time, 'sleep'):
            result = h.main(event({'playlist_id': 'PLx'}, None, dict(OTHER, **{'X-Forwarded-For': '1.1.1.1'})), None)
        self.assertEqual(json.loads(result['body']), {'title': 'a "quoted" title'})

    def test_regist_without_body_is_bad_request(self):
        h = self.handlers['post_yt_channel_regist']
        for body in (None, 'not json', json.dumps({'channel_id': 123})):
            with self.subTest(body=body):
                self.assertEqual(h.main(event(body=body), None)['statusCode'], 400)

    def test_regist_unknown_channel_is_bad_request(self):
        h = self.handlers['post_yt_channel_regist']
        with patch.object(self.ddb, 'isExistChannelID', return_value=(False, '')), \
                patch.object(self.yt, 'getRSS', side_effect=OSError('404')):
            result = h.main(event(body=json.dumps({'channel_id': UC})), None)
        self.assertEqual(json.loads(result['body'])['error'], 'channel not exist')

    def test_scraping_rss(self):
        feed = ET.fromstring(
            '<feed xmlns="http://www.w3.org/2005/Atom"><author><name>ch</name></author>'
            '<entry><title>v1</title><link href="https://youtu.be/1"/><author><name>x</name></author></entry>'
            '<entry><title>v2</title><link href="https://youtu.be/2"/></entry></feed>')
        self.assertEqual(self.yt.scrapingRSS(feed), ('ch', ['https://youtu.be/1', 'https://youtu.be/2'], ['v1', 'v2']))


class QuotaUsageTests(OfflineTestCase):
    def test_api_calls_record_cost_even_on_failure(self):
        youtube = MagicMock()
        youtube.search.return_value.list.return_value.execute.return_value = {'items': []}
        with patch.object(self.yt, '_youtube', return_value=youtube), \
                patch.object(self.ddb, 'add_quota_usage') as usage:
            self.yt.ytapi_search_query('q')
            youtube.channels.return_value.list.return_value.execute.side_effect = OSError('down')
            with self.assertRaises(OSError):
                self.yt.ytapi_channel_id_by_handle('x')
        self.assertEqual([c.args for c in usage.call_args_list], [('search', 100), ('channels', 1)])

    def test_usage_is_added_per_utc_hour_and_never_raises(self):
        self.ddb.add_quota_usage('search', 100)
        args = self.table.update_item.call_args.kwargs
        hour = self.ddb.datetime.datetime.now(self.ddb.datetime.timezone.utc).strftime(self.ddb.HOURLY)
        self.assertEqual(args['Key'], {'user_id': 'yt_quota_usage', 'video_id': hour})
        self.assertEqual(args['ExpressionAttributeNames']['#api'], 'search')
        self.table.update_item.side_effect = OSError('ddb down')
        self.ddb.add_quota_usage('search', 100)

    def test_pacific_day_start_follows_dst(self):
        h = self.handlers['notify_yt_quota']
        utc = h.datetime.timezone.utc
        for now, expected in (((2026, 10, 22, 3), (2026, 10, 21, 7)),   # PDT: 0時 = 7:00 UTC
                              ((2026, 12, 1, 9), (2026, 12, 1, 8)),    # PST: 0時 = 8:00 UTC
                              ((2026, 3, 8, 9), (2026, 3, 8, 8)),      # 夏時間開始日 (2:00 PST まで PST)
                              ((2026, 11, 1, 8), (2026, 11, 1, 7))):   # 夏時間終了日 (2:00 PDT まで PDT)
            with self.subTest(now=now):
                start = h.pacific_day_start(h.datetime.datetime(*now, tzinfo=utc))
                self.assertEqual(start, h.datetime.datetime(*expected, tzinfo=utc))

    def test_message_has_last_hour_breakdown_and_daily_total(self):
        h = self.handlers['notify_yt_quota']
        now = h.datetime.datetime(2026, 10, 22, 3, 0, 5, tzinfo=h.datetime.timezone.utc)
        items = [
            {'user_id': 'yt_quota_usage', 'video_id': '2026102106', 'total': 999, 'TTL': 1},  # 前日分
            {'user_id': 'yt_quota_usage', 'video_id': '2026102107', 'total': 7000, 'search': 7000, 'TTL': 1},
            {'user_id': 'yt_quota_usage', 'video_id': '2026102202', 'total': 1104, 'search': 1100,
             'playlistItems': 4, 'TTL': 1},
        ]
        with patch.object(self.ddb, 'getQuotaUsage', return_value=items) as query:
            embed = h.build_embed(now)
        query.assert_called_once_with('2026102107', '2026102203')
        self.assertEqual(embed['fields'], [
            {'name': '直近1時間 (10/22 11:00〜12:00 JST)', 'value': '`1,104 unit`', 'inline': False},
            {'name': 'playlistItems', 'value': '`4`', 'inline': True},
            {'name': 'search', 'value': '`1,100`', 'inline': True},
        ])
        self.assertEqual(embed['description'], '**本日累計: 8,104 / 10,000 unit (81%)**')
        self.assertTrue(embed['title'].startswith('⚠️'))
        self.assertEqual(embed['color'], h.WARN_COLOR)
        self.assertIn('10/21 16:00 JST', embed['footer']['text'])
        # 使用が無かった時間も 0 unit を表示
        with patch.object(self.ddb, 'getQuotaUsage', return_value=[]):
            embed = h.build_embed(now)
        self.assertEqual([f['value'] for f in embed['fields']], ['`0 unit`'])
        self.assertEqual(embed['color'], h.COLOR)

    def test_message_after_reset_has_previous_day_total(self):
        h = self.handlers['notify_yt_quota']
        # 16:00 JST (PDT 0時) の通知: 直前の1時間は前日分
        now = h.datetime.datetime(2026, 10, 22, 7, 0, 5, tzinfo=h.datetime.timezone.utc)
        items = [
            {'user_id': 'yt_quota_usage', 'video_id': '2026102107', 'total': 300, 'TTL': 1},
            {'user_id': 'yt_quota_usage', 'video_id': '2026102206', 'total': 18, 'videos': 6, 'TTL': 1},
        ]
        with patch.object(self.ddb, 'getQuotaUsage', return_value=items) as query:
            embed = h.build_embed(now)
        query.assert_called_once_with('2026102107', '2026102207')
        self.assertEqual(embed['fields'][0], {
            'name': '前日の最終累計 (10/21 16:00 JST〜)', 'value': '`318 / 10,000 unit (3%)`', 'inline': False})
        self.assertEqual(embed['fields'][1]['value'], '`18 unit`')
        self.assertEqual(embed['description'], '**本日累計: 0 / 10,000 unit (0%)**')
        # リセット直後以外は載せない
        with patch.object(self.ddb, 'getQuotaUsage', return_value=[]):
            embed = h.build_embed(now + h.datetime.timedelta(hours=1))
        self.assertNotIn('前日', embed['fields'][0]['name'])

    def test_discord_post_needs_url(self):
        h = self.notifier
        with patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': ''}), \
                patch.object(h.urllib.request, 'urlopen') as urlopen:
            h.post_discord({'content': 'x'})
        urlopen.assert_not_called()
        with patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'https://discord.invalid/webhook'}), \
                patch.object(h.urllib.request, 'urlopen') as urlopen:
            h.post_discord({'embeds': [{'title': 'こんにちは'}]})
        request = urlopen.call_args.args[0]
        self.assertEqual(json.loads(request.data), {'embeds': [{'title': 'こんにちは'}]})
        self.assertIn('User-agent', request.headers)


class AccessStatsTests(OfflineTestCase):
    def test_add_access_per_jst_day(self):
        self.ddb.add_access('channel', UC, 'ch', refreshed=True)
        args = self.table.update_item.call_args.kwargs
        day = self.ddb.datetime.datetime.now(self.ddb.JST).strftime(self.ddb.DAILY)
        self.assertEqual(args['Key'], {'user_id': f'access_stats_{day}', 'video_id': f'channel#{UC}'})
        self.assertTrue(args['UpdateExpression'].startswith('ADD #count :one, #refresh :one SET'))
        self.assertEqual(args['ExpressionAttributeValues'][':name'], 'ch')
        self.ddb.add_access('search', 'q')
        args = self.table.update_item.call_args.kwargs
        self.assertNotIn('#refresh', args['ExpressionAttributeNames'])
        self.assertNotIn('#name', args['ExpressionAttributeNames'])
        self.table.update_item.side_effect = OSError('ddb down')
        self.ddb.add_access('search', 'q')

    def test_video_list_records_access_and_refresh(self):
        now = self.ddb.datetime.datetime.now().strftime(self.ddb.HOURLY)
        fresh = dict(videos(1), latest_update=now, limit=50, auther='ch')
        data = {'playlistId': 'PLx', 'playlist_title': 'pl', 'videos': videos(1)}
        with patch.object(self.ddb, 'add_access') as access:
            with patch.object(self.ddb, 'getVideoList', return_value=fresh):
                self.vl.channel_videos(UC)
            with patch.object(self.ddb, 'getPlaylistVideos', return_value=None), \
                    patch.object(self.yt, 'ytapi_search_playlist', return_value=data), \
                    patch.object(self.ddb, 'registPlaylistVideos'):
                self.vl.playlist_videos('PLx')
            with patch.object(self.ddb, 'getQueryVideoList', return_value=None), \
                    patch.object(self.yt, 'ytapi_search_query', side_effect=OSError('down')), \
                    self.assertRaises(OSError):
                self.vl.query_videos('q')
        self.assertEqual([c.args for c in access.call_args_list],
                         [('channel', UC, 'ch', False), ('playlist', 'PLx', 'pl', True)])

    def test_summary_lists_top_targets(self):
        h = self.handlers['notify_access_summary']
        items = [{'kind': 'channel', 'target': f'UC{i}', 'name': f'ch{i}', 'count': i} for i in range(1, 13)]
        items += [{'kind': 'search', 'target': 'a*b_c', 'count': 3, 'refresh': 1},
                  {'kind': 'playlist', 'target': 'PLx', 'name': '', 'count': 2}]
        day = h.datetime.date(2026, 10, 21)
        with patch.object(self.ddb, 'getAccessStats', return_value=items) as stats, \
                patch.object(self.ddb, 'getQuotaUsage', return_value=[{'total': 100}, {'total': 23}]) as quota:
            embed = h.build_embed(day)
        stats.assert_called_once_with('20261021')
        # JSTの1日 = 前日15:00〜当日14:00 UTC
        quota.assert_called_once_with('2026102015', '2026102114')
        channel, playlist, search = embed['fields']
        self.assertEqual(channel['name'], '📺 チャンネル (12件 / 78回)')
        self.assertEqual(channel['value'].splitlines()[0], '1. ch12 `12回`')
        self.assertEqual(len(channel['value'].splitlines()), 10)
        self.assertEqual(playlist['value'], '1. PLx `2回`')
        self.assertEqual(search['value'], '1. a\\*b\\_c `3回` (更新1)')
        self.assertEqual(embed['description'], '**アクセス 83回** / YouTube API 123 unit (概算)')
        with patch.object(self.ddb, 'getAccessStats', return_value=[]), \
                patch.object(self.ddb, 'getQuotaUsage', return_value=[]):
            self.assertEqual([f['value'] for f in h.build_embed(day)['fields']], ['なし'] * 3)

    def test_get_access_stats_follows_pages(self):
        self.table.query.side_effect = [{'Items': [1], 'LastEvaluatedKey': 'k'}, {'Items': [2]}]
        self.assertEqual(self.ddb.getAccessStats('20261021'), [1, 2])
        self.assertEqual(self.table.query.call_args.kwargs['ExclusiveStartKey'], 'k')


class ChannelIdTests(OfflineTestCase):
    def setUp(self):
        super().setUp()
        for name, value in (('getChannelAlias', None), ('registChannelAlias', None)):
            p = patch.object(self.ddb, name, return_value=value)
            setattr(self, name, p.start())
            self.addCleanup(p.stop)

    def test_parse_inputs(self):
        cases = {
            '@SUSURUTV': ('handle', 'SUSURUTV'),
            'https://www.youtube.com/@SUSURUTV/videos': ('handle', 'SUSURUTV'),
            'youtube.com/@からあげクン': ('handle', 'からあげクン'),
            f'https://www.youtube.com/channel/{UC}': ('channel', UC),
            'https://www.youtube.com/user/GoogleDevelopers': ('username', 'GoogleDevelopers'),
            'https://m.youtube.com/c/GoogleDevelopers': ('custom', 'GoogleDevelopers'),
            'https://www.youtube.com/GoogleDevelopers': ('custom', 'GoogleDevelopers'),
            'https://www.youtube.com/watch?v=LVwxCaFySN0&t=10': ('video', 'LVwxCaFySN0'),
            'https://youtu.be/LVwxCaFySN0?si=x': ('video', 'LVwxCaFySN0'),
            'https://www.youtube.com/shorts/LVwxCaFySN0': ('video', 'LVwxCaFySN0'),
            'https://example.com/@SUSURUTV': None,
            'https://www.youtube.com/playlist?list=PLx': None,
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(self.ch._parse(value, allow_url=True), expected)

    def test_path_accepts_only_id_and_handle(self):
        self.assertEqual(self.ch._parse('@SUSURUTV', allow_url=False), ('handle', 'SUSURUTV'))
        self.assertIsNone(self.ch._parse('https://www.youtube.com/@SUSURUTV', allow_url=False))
        self.assertIsNone(self.ch.resolve('UCx'))

    def test_uc_id_needs_no_lookup(self):
        with patch.object(self.yt, 'ytapi_channel_id_by_handle') as api:
            self.assertEqual(self.ch.resolve(f' {UC} '), UC)
        api.assert_not_called()
        self.getChannelAlias.assert_not_called()

    def test_url_encoded_handle_is_resolved_and_cached(self):
        with patch.object(self.yt, 'ytapi_channel_id_by_handle', return_value=UC) as api:
            self.assertEqual(self.ch.resolve('%40%E3%81%8B%E3%82%89%E3%81%82%E3%81%92%E3%82%AF%E3%83%B3'), UC)
        api.assert_called_once_with('からあげクン')
        alias, channel_id, ttl = self.registChannelAlias.call_args.args
        self.assertEqual((alias, channel_id), ('handle:からあげクン', UC))
        self.assertAlmostEqual(ttl, self.ddb.ttl_after(days=7), delta=5)

    def test_handle_cache_is_case_insensitive_and_skips_api(self):
        self.getChannelAlias.return_value = {'channel_id': UC}
        with patch.object(self.yt, 'ytapi_channel_id_by_handle') as api:
            self.assertEqual(self.ch.resolve('@SusuruTV'), UC)
        self.getChannelAlias.assert_called_once_with('handle:susurutv')
        api.assert_not_called()

    def test_not_found_is_cached_briefly(self):
        with patch.object(self.yt, 'ytapi_channel_id_by_handle', return_value=None):
            self.assertIsNone(self.ch.resolve('@nobody'))
        alias, channel_id, ttl = self.registChannelAlias.call_args.args
        self.assertEqual(channel_id, '')
        self.assertAlmostEqual(ttl, self.ddb.ttl_after(hours=1), delta=5)
        self.getChannelAlias.return_value = {'channel_id': ''}
        with patch.object(self.yt, 'ytapi_channel_id_by_handle') as api:
            self.assertIsNone(self.ch.resolve('@nobody'))
        api.assert_not_called()

    def test_api_failure_is_not_cached(self):
        with patch.object(self.yt, 'ytapi_channel_id_by_handle', side_effect=OSError('down')):
            self.assertIsNone(self.ch.resolve('@SUSURUTV'))
        self.registChannelAlias.assert_not_called()

    def test_each_kind_uses_its_lookup(self):
        for value, target in (('https://youtube.com/user/GoogleDevelopers', 'ytapi_channel_id_by_username'),
                              ('https://youtu.be/LVwxCaFySN0', 'ytapi_channel_id_by_video'),
                              ('https://youtube.com/c/GoogleDevelopers', 'scrape_channel_id')):
            with self.subTest(target=target), patch.object(self.yt, target, return_value=UC2) as lookup:
                self.assertEqual(self.ch.resolve(value, allow_url=True), UC2)
                lookup.assert_called_once()

    def test_scrape_reads_canonical(self):
        html = f'<html><link rel="canonical" href="https://www.youtube.com/channel/{UC2}"></html>'.encode()
        response = MagicMock()
        response.__enter__.return_value.read.return_value = html
        with patch.object(self.yt.urllib.request, 'urlopen', return_value=response):
            self.assertEqual(self.yt.scrape_channel_id('https://www.youtube.com/c/GoogleDevelopers'), UC2)

    def test_handle_in_path_works_like_uc(self):
        h = self.handlers['get_yt_channel']
        with patch.object(self.ch, 'resolve', return_value=UC), \
                patch.object(self.vl, 'channel_videos', return_value=videos(2)) as load_videos:
            result = h.main(event({'channel_id': '@SUSURUTV'}, {'n': '1'}, PC), None)
        load_videos.assert_called_once_with(UC, limit=50)
        self.assertEqual(result['headers']['location'], 'https://youtu.be/1')

    def test_unresolved_path_is_not_found(self):
        with patch.object(self.ch, 'resolve', return_value=None):
            for name in ('get_yt_channel', 'get_yt_ch_continuous_play', 'get_ytlive_channel'):
                with self.subTest(name=name):
                    result = self.handlers[name].main(event({'channel_id': '@nobody'}, {'n': '0'}, PC), None)
                    self.assertEqual(result['headers']['location'], NF)
            self.assertEqual(self.handlers['get_yt_channel_list'].main(event({'channel_id': '@nobody'}), None)['statusCode'], 404)
            self.assertEqual(self.handlers['get_yt_ch_all'].main(event({'channel_id': '@nobody'}), None)['statusCode'], 404)

    def test_regist_accepts_url_and_returns_channel_id(self):
        h = self.handlers['post_yt_channel_regist']
        with patch.object(self.ch, 'resolve', return_value=UC) as resolve, \
                patch.object(self.ddb, 'isExistChannelID', return_value=(True, 'SUSURU TV.')):
            result = h.main(event(body=json.dumps({'channel_id': 'https://www.youtube.com/@SUSURUTV'})), None)
        resolve.assert_called_once_with('https://www.youtube.com/@SUSURUTV', allow_url=True)
        self.assertEqual(json.loads(result['body']), {'result': 'OK', 'auther': 'SUSURU TV.', 'channel_id': UC})

    def test_resolve_api(self):
        h = self.handlers['get_yt_ch_resolve']
        with patch.object(self.ch, 'resolve', return_value=UC):
            result = h.main(event(query={'q': '@SUSURUTV'}), None)
        self.assertEqual(json.loads(result['body']), {'result': 'OK', 'channel_id': UC})
        with patch.object(self.ch, 'resolve', return_value=None):
            self.assertEqual(h.main(event(query={'q': '@nobody'}), None)['statusCode'], 404)


if __name__ == '__main__':
    unittest.main()
