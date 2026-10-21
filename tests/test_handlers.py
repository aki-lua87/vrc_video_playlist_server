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
            cls.yt = load('t_ytutils', f'{LAYER}/ytutils.py')
            cls.http = load('t_httputils', f'{LAYER}/httputils.py')
            layer = {'ddbutils': cls.ddb, 'ytutils': cls.yt, 'httputils': cls.http}
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
        self.assertEqual(len(self.handlers), 16)

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
            self.assertIs(self.vl.channel_videos(UC), record)
        api.assert_not_called()

    def test_stale_cache_is_used_when_api_fails(self):
        record = dict(videos(2), latest_update='2000010100')
        with patch.object(self.ddb, 'getVideoList', return_value=record), \
                patch.object(self.yt, 'ytapi_search_channelId', side_effect=OSError('down')):
            self.assertIs(self.vl.channel_videos(UC), record)

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
        self.assertEqual(result, dict(videos(1), live='https://youtu.be/live'))

    def test_pick(self):
        self.assertEqual(self.vl.pick(videos(2), 1), ('https://youtu.be/1', 't1'))
        self.assertIsNone(self.vl.pick(videos(2), 2))
        self.assertIsNone(self.vl.pick(None, 0))


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
        load_videos.assert_called_once_with(UC)
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
