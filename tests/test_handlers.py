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
            cls.yt = load('t_ytutils', f'{LAYER}/ytutils.py')
            cls.http = load('t_httputils', f'{LAYER}/httputils.py')
            layer = {'ddbutils': cls.ddb, 'ytutils': cls.yt, 'httputils': cls.http}
            with patch.dict(sys.modules, layer):
                cls.vl = load('t_videolist', f'{LAYER}/videolist.py')
            cls.handlers = {}
            with patch.dict(sys.modules, dict(layer, videolist=cls.vl)):
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
        self.assertEqual(len(self.handlers), 15)

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

    def test_title_json_escapes_quotes(self):
        title = '激辛 "ブルダック" \\ test'
        body = self.http.title_json(title)['body']
        self.assertEqual(json.loads(body), {'title': title})


class VideoListTests(OfflineTestCase):
    def test_fresh_cache_does_not_call_api(self):
        record = dict(videos(2), latest_update=self.ddb.datetime.datetime.now().strftime(self.ddb.HOURLY))
        with patch.object(self.ddb, 'getVideoList', return_value=record), \
                patch.object(self.yt, 'ytapi_search_channelId') as api:
            self.assertIs(self.vl.channel_videos('UCx'), record)
        api.assert_not_called()

    def test_stale_cache_is_used_when_api_fails(self):
        record = dict(videos(2), latest_update='2000010100')
        with patch.object(self.ddb, 'getVideoList', return_value=record), \
                patch.object(self.yt, 'ytapi_search_channelId', side_effect=OSError('down')):
            self.assertIs(self.vl.channel_videos('UCx'), record)

    def test_missing_cache_and_api_failure_raises(self):
        with patch.object(self.ddb, 'getQueryVideoList', return_value=None), \
                patch.object(self.yt, 'ytapi_search_query', side_effect=OSError('down')), \
                self.assertRaises(OSError):
            self.vl.query_videos('q')

    def test_unregistered_channel_is_not_fetched_when_disabled(self):
        with patch.object(self.ddb, 'getVideoList', return_value=None), \
                patch.object(self.yt, 'ytapi_search_channelId') as api:
            self.assertIsNone(self.vl.channel_videos('UCx', fetch_if_missing=False))
        api.assert_not_called()

    def test_refresh_returns_api_videos_with_live(self):
        data = {'channelId': 'UCx', 'auther': 'a', 'live': {'title': 'L', 'url': 'https://youtu.be/live'}, 'videos': videos(1)}
        with patch.object(self.ddb, 'getVideoList', return_value=None), \
                patch.object(self.yt, 'ytapi_search_channelId', return_value=data), \
                patch.object(self.ddb, 'registVideoListV2') as save:
            result = self.vl.channel_videos('UCx', index_create=False)
        save.assert_called_once_with(data, False)
        self.assertEqual(result, dict(videos(1), live='https://youtu.be/live'))

    def test_pick(self):
        self.assertEqual(self.vl.pick(videos(2), 1), ('https://youtu.be/1', 't1'))
        self.assertIsNone(self.vl.pick(videos(2), 2))
        self.assertIsNone(self.vl.pick(None, 0))


class VideoHandlerTests(OfflineTestCase):
    def test_out_of_range_index_redirects_to_not_found(self):
        h = self.handlers['get_yt_channel']
        with patch.object(self.vl, 'channel_videos', return_value=videos(2)):
            result = h.main(event({'channel_id': 'UCx'}, {'n': '5'}, PC), None)
        self.assertEqual(result['headers']['location'], NF)

    def test_api_failure_without_cache_redirects_to_not_found(self):
        for name, target in (('get_yt_channel', 'channel_videos'), ('get_yt_playlist', 'playlist_videos'),
                             ('get_yt_query', 'query_videos')):
            with self.subTest(name=name), patch.object(self.vl, target, side_effect=OSError('down')):
                path = {'channel_id': 'UCx', 'playlist_id': 'PLx'}
                result = self.handlers[name].main(event(path, {'n': '0', 'q': 'x'}, QUEST), None)
                self.assertEqual(result['headers']['location'], NF)

    def test_invalid_index_is_bad_request(self):
        for n in ('abc', '-1'):
            with self.subTest(n=n):
                result = self.handlers['get_yt_channel'].main(event({'channel_id': 'UCx'}, {'n': n}, PC), None)
                self.assertEqual(result['statusCode'], 400)

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
            result = h.main(event({'channel_id': 'UCx'}, None, {'User-Agent': 'curl'}), None)
        self.assertEqual(result['statusCode'], 404)

    def test_channel_titles_registered_without_list_does_not_crash(self):
        h = self.handlers['get_yt_channel_list']
        with patch.object(self.ddb, 'isExistChannelID', return_value=(True, 'a')), \
                patch.object(self.ddb, 'getVideoList', return_value=None), \
                patch.object(self.yt, 'ytapi_search_channelId', side_effect=OSError('down')):
            result = h.main(event({'channel_id': 'UCx'}, None, {'User-Agent': 'curl'}), None)
        self.assertEqual(result['statusCode'], 302)
        self.assertEqual(result['headers']['location'], f'{CF}/yt/list/UCx.mp4')

    def test_channel_titles_v2_and_loader_for_unregistered(self):
        h = self.handlers['get_yt_channel_list']
        with patch.object(self.ddb, 'getVideoList', return_value=None):
            self.assertEqual(h.main(event({'channel_id': 'UCx'}, {'version': 'v2'}), None)['body'], 'null')
            self.assertEqual(h.main(event({'channel_id': 'UCx'}, None, OTHER), None)['body'], '')

    def test_chs_description_skips_unregistered_channel(self):
        h = self.handlers['get_yt_chs_description']
        with patch.object(self.vl, 'channel_videos', side_effect=[videos(2), None]):
            result = h.main(event(query={'targets': 'UCa,UCb'}), None)
        self.assertEqual(result['body'], 'UCa:t0,t1\nUCb:')

    def test_live_redirect(self):
        h = self.handlers['get_ytlive_channel']
        with patch.object(self.vl, 'channel_videos', return_value={'live': 'https://youtu.be/live'}):
            self.assertEqual(h.main(event({'channel_id': 'UCx'}), None)['headers']['location'], 'https://youtu.be/live')
        with patch.object(self.vl, 'channel_videos', return_value={'live': ''}):
            self.assertEqual(h.main(event({'channel_id': 'UCx'}), None)['headers']['location'], NF)


class ContinuousAndRegistTests(OfflineTestCase):
    def test_channel_continuous_wraps_after_last_video(self):
        h = self.handlers['get_yt_ch_continuous_play']
        record = dict(videos(3), ip_address='1.1.1.1', _count=2)
        with patch.object(self.ddb, 'isExistContinuousChannelID', return_value=record), \
                patch.object(self.ddb, 'countupContinuousChannelID', return_value=3):
            result = h.main(event({'channel_id': 'UCx'}, None, dict(PC, **{'X-Forwarded-For': '1.1.1.1, 2.2.2.2'})), None)
        self.assertEqual(result['headers']['location'], 'https://youtu.be/0')

    def test_channel_continuous_empty_channel_is_not_found(self):
        h = self.handlers['get_yt_ch_continuous_play']
        data = {'channelId': 'UCx', 'auther': '', 'live': {'url': ''}, 'videos': videos(0)}
        with patch.object(self.ddb, 'isExistContinuousChannelID', return_value=None), \
                patch.object(self.yt, 'ytapi_search_channelId', return_value=data), \
                patch.object(self.ddb, 'regist_continuous_channel_video_list') as save:
            result = h.main(event({'channel_id': 'UCx'}, None, PC), None)
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
            result = h.main(event(body=json.dumps({'channel_id': 'UCx'})), None)
        self.assertEqual(json.loads(result['body'])['error'], 'channel not exist')

    def test_scraping_rss(self):
        feed = ET.fromstring(
            '<feed xmlns="http://www.w3.org/2005/Atom"><author><name>ch</name></author>'
            '<entry><title>v1</title><link href="https://youtu.be/1"/><author><name>x</name></author></entry>'
            '<entry><title>v2</title><link href="https://youtu.be/2"/></entry></feed>')
        self.assertEqual(self.yt.scrapingRSS(feed), ('ch', ['https://youtu.be/1', 'https://youtu.be/2'], ['v1', 'v2']))


if __name__ == '__main__':
    unittest.main()
