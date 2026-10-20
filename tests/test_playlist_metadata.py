"""Offline regression tests. No AWS/YouTube credentials or SDK installs needed.

Only SDK import boundaries are stubbed; the repository's handlers, API helper,
pagination and DynamoDB request construction run as implemented.
"""
import contextlib
import copy
from datetime import datetime, timedelta
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
PLAYLIST_ID = 'PL123456789012345'
TODAY = datetime.now().strftime('%Y%m%d')


class HttpError(Exception):
    def __init__(self, status=503, reason='backendError'):
        self.resp = types.SimpleNamespace(status=status)
        self.content = json.dumps({'error': {'errors': [{'reason': reason}]}}).encode()


class HttpLib2Error(Exception):
    pass


def module(name, **attributes):
    result = types.ModuleType(name)
    result.__dict__.update(attributes)
    return result


def load(name, relative_path):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class PlaylistMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table = MagicMock()
        boto = module('boto3', resource=MagicMock())
        boto.resource.return_value.Table.return_value = cls.table
        dependencies = {
            'boto3': boto,
            'boto3.dynamodb': module('boto3.dynamodb'),
            'boto3.dynamodb.conditions': module('boto3.dynamodb.conditions', Key=MagicMock()),
            'googleapiclient': module('googleapiclient'),
            'googleapiclient.discovery': module('googleapiclient.discovery', build=MagicMock()),
            'googleapiclient.errors': module('googleapiclient.errors', HttpError=HttpError),
            'httplib2': module('httplib2', HttpLib2Error=HttpLib2Error)
        }
        with patch.dict(sys.modules, dependencies), patch.dict(os.environ, {
            'VRC_VIDEO_TABLE': 'offline-table', 'API_KEY': 'offline-only',
            'CF_DOMAIN': 'https://example.invalid'
        }):
            cls.yt = load('offline_ytutils', 'src/layers/utils/python/ytutils.py')
            cls.ddb = load('offline_ddbutils', 'src/layers/utils/python/ddbutils.py')
            cls.http = load('offline_httputils', 'src/layers/utils/python/httputils.py')
            with patch.dict(sys.modules, {'ytutils': cls.yt, 'ddbutils': cls.ddb, 'httputils': cls.http}):
                cls.videolist = load('offline_videolist', 'src/layers/utils/python/videolist.py')
            with patch.dict(sys.modules, {'ytutils': cls.yt, 'ddbutils': cls.ddb, 'httputils': cls.http,
                                          'videolist': cls.videolist}):
                cls.handler = load('offline_titles', 'src/lambda/get_yt_playlist_titles/handler.py')
                cls.video = load('offline_video', 'src/lambda/get_yt_playlist/handler.py')
                cls.continuous = load('offline_register', 'src/lambda/get_yt_pl_continuous_play_regist/handler.py')

    def setUp(self):
        self.env = patch.dict(os.environ, {'API_KEY': 'offline-only'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)
        self.table.reset_mock(return_value=True, side_effect=True)
        self.data = {
            'playlistId': PLAYLIST_ID, 'playlist_title': '日本語 "リスト"',
            'videos': {'titles': ['A', 'B'], 'urls': ['https://example.invalid/a', 'https://example.invalid/b']}
        }
        self.record = {
            'user_id': 'list_yt_pl', 'video_id': PLAYLIST_ID,
            'latest_update': TODAY, 'playlist_title_checked': TODAY,
            'playlist_title': self.data['playlist_title'], **copy.deepcopy(self.data['videos'])
        }

    def test_metadata_uses_official_api_and_preserves_unicode_quotes(self):
        youtube = MagicMock()
        youtube.playlists.return_value.list.return_value.execute.return_value = {
            'items': [{'snippet': {'title': '  日本語 "リスト"  '}}]
        }
        self.assertEqual(self.yt.ytapi_playlist_title(PLAYLIST_ID, youtube), '日本語 "リスト"')
        youtube.playlists.return_value.list.assert_called_once_with(
            part='snippet', id=PLAYLIST_ID, fields='items(id,snippet/title)')

    def test_missing_metadata_returns_empty_name(self):
        for result in ({'items': []}, {'items': [{'snippet': {}}]}, {'items': [{'snippet': {'title': None}}]}):
            with self.subTest(result=result):
                youtube = MagicMock()
                youtube.playlists.return_value.list.return_value.execute.return_value = result
                self.assertEqual(self.yt.ytapi_playlist_title(PLAYLIST_ID, youtube), '')

    def test_expected_metadata_failures_return_empty_name(self):
        for error in (HttpError(403), HttpError(404), OSError('timeout'), HttpLib2Error('transport')):
            with self.subTest(error=type(error).__name__):
                youtube = MagicMock()
                youtube.playlists.return_value.list.return_value.execute.side_effect = error
                self.assertEqual(self.yt.ytapi_playlist_title(PLAYLIST_ID, youtube), '')

    def test_programming_errors_are_not_swallowed(self):
        youtube = MagicMock()
        youtube.playlists.return_value.list.return_value.execute.side_effect = RuntimeError('bug')
        with self.assertRaises(RuntimeError):
            self.yt.ytapi_playlist_title(PLAYLIST_ID, youtube)

    def api_client(self, metadata_error=None, empty=False):
        youtube = MagicMock()
        first, second = MagicMock(), MagicMock()

        def item(title, video_id):
            return {'snippet': {'title': title, 'resourceId': {'videoId': video_id}}}
        first.execute.return_value = {'items': [] if empty else [item('first', 'one'), item('second', 'two')]}
        second.execute.return_value = {'items': [item('third', 'three')]}
        youtube.playlistItems.return_value.list.return_value = first
        youtube.playlistItems.return_value.list_next.side_effect = [None] if empty else [second, None]
        metadata = youtube.playlists.return_value.list.return_value.execute
        metadata.return_value = {'items': [{'snippet': {'title': '日本語 "リスト"'}}]}
        metadata.side_effect = metadata_error
        return youtube

    def test_multiple_pages_keep_order_and_fetch_name_once(self):
        youtube = self.api_client()
        with patch.object(self.yt, 'build', return_value=youtube):
            result = self.yt.ytapi_search_playlist(PLAYLIST_ID)
        self.assertEqual(result['playlistId'], PLAYLIST_ID)
        self.assertEqual(result['playlist_title'], self.data['playlist_title'])
        self.assertEqual(result['videos']['titles'], ['first', 'second', 'third'])
        self.assertEqual(result['videos']['urls'], ['https://www.youtube.com/watch?v=' + x for x in ['one', 'two', 'three']])
        youtube.playlists.return_value.list.assert_called_once()

    def test_metadata_failure_keeps_successful_video_list(self):
        with patch.object(self.yt, 'build', return_value=self.api_client(HttpError(503))):
            result = self.yt.ytapi_search_playlist(PLAYLIST_ID)
        self.assertEqual(result['playlist_title'], '')
        self.assertEqual(result['videos']['titles'], ['first', 'second', 'third'])

    def test_empty_playlist_remains_valid_api_response(self):
        with patch.object(self.yt, 'build', return_value=self.api_client(empty=True)):
            result = self.yt.ytapi_search_playlist(PLAYLIST_ID)
        self.assertEqual(result['videos'], {'titles': [], 'urls': []})

    def test_video_api_failure_is_not_hidden_by_metadata_fallback(self):
        youtube = self.api_client()
        youtube.playlistItems.return_value.list.return_value.execute.side_effect = HttpError(404)
        with patch.object(self.yt, 'build', return_value=youtube), self.assertRaises(HttpError):
            self.yt.ytapi_search_playlist(PLAYLIST_ID)
        youtube.playlists.assert_not_called()

    def test_database_write_includes_name_and_attempt_date(self):
        self.ddb.registPlaylistVideos(self.data)
        item = self.table.put_item.call_args.kwargs['Item']
        self.assertEqual(item['playlist_title'], self.data['playlist_title'])
        self.assertEqual(item['playlist_title_checked'], TODAY)
        self.assertEqual(item['urls'], self.data['videos']['urls'])

    def test_database_write_accepts_older_callers(self):
        self.data.pop('playlist_title')
        self.ddb.registPlaylistVideos(self.data)
        self.assertEqual(self.table.put_item.call_args.kwargs['Item']['playlist_title'], '')

    def test_database_backfill_does_not_replace_video_list_or_create_orphan(self):
        self.table.update_item.return_value = {'Attributes': self.record}
        self.assertEqual(self.ddb.updatePlaylistTitle(PLAYLIST_ID, 'name', TODAY), self.record)
        args = self.table.update_item.call_args.kwargs
        self.assertEqual(set(args['ExpressionAttributeNames'].values()), {'playlist_title', 'playlist_title_checked'})
        self.assertEqual(args['ConditionExpression'], 'attribute_exists(user_id) AND attribute_exists(video_id)')
        self.table.put_item.assert_not_called()

    def test_cache_miss_returns_new_name_and_original_arrays(self):
        with patch.object(self.ddb, 'getPlaylistVideos', return_value=None), \
                patch.object(self.yt, 'ytapi_search_playlist', return_value=self.data), \
                patch.object(self.ddb, 'registPlaylistVideos') as save:
            result = self.handler.getVideoURL(PLAYLIST_ID)
        self.assertEqual(result, dict(self.data['videos'], playlist_title=self.data['playlist_title']))
        save.assert_called_once_with(self.data)

    def test_current_cache_makes_no_youtube_request_and_preserves_old_fields(self):
        with patch.object(self.ddb, 'getPlaylistVideos', return_value=self.record), \
                patch.object(self.yt, 'ytapi_playlist_title') as name, \
                patch.object(self.yt, 'ytapi_search_playlist') as videos:
            result = self.handler.getVideoURL(PLAYLIST_ID)
        name.assert_not_called()
        videos.assert_not_called()
        self.assertEqual(result['user_id'], 'list_yt_pl')
        self.assertEqual(result['latest_update'], TODAY)
        self.assertNotIn('playlist_title_checked', result)
        self.assertIn('playlist_title_checked', self.record)  # Do not mutate cached record.

    def test_legacy_cache_backfills_name_without_refetching_videos(self):
        legacy = dict(self.record)
        legacy.pop('playlist_title')
        legacy.pop('playlist_title_checked')
        with patch.object(self.ddb, 'getPlaylistVideos', return_value=legacy), \
                patch.object(self.yt, 'ytapi_playlist_title', return_value=self.data['playlist_title']) as name, \
                patch.object(self.ddb, 'updatePlaylistTitle', return_value=self.record) as update, \
                patch.object(self.yt, 'ytapi_search_playlist') as videos:
            result = self.handler.getVideoURL(PLAYLIST_ID)
        name.assert_called_once_with(PLAYLIST_ID)
        update.assert_called_once_with(PLAYLIST_ID, self.data['playlist_title'], TODAY)
        videos.assert_not_called()
        self.assertEqual(result['urls'], legacy['urls'])

    def test_failed_name_backfill_is_not_retried_same_day(self):
        legacy = dict(self.record)
        legacy.pop('playlist_title_checked')
        failed = dict(self.record, playlist_title='')
        with patch.object(self.ddb, 'getPlaylistVideos', side_effect=[legacy, failed]), \
                patch.object(self.yt, 'ytapi_playlist_title', return_value='') as name, \
                patch.object(self.ddb, 'updatePlaylistTitle', return_value=failed):
            self.assertEqual(self.handler.getVideoURL(PLAYLIST_ID)['playlist_title'], '')
            self.assertEqual(self.handler.getVideoURL(PLAYLIST_ID)['playlist_title'], '')
        name.assert_called_once()

    def test_stale_name_is_cleared_when_current_list_refresh_has_no_name(self):
        stale = dict(self.record, latest_update=(datetime.now() - timedelta(days=1)).strftime('%Y%m%d'))
        refreshed = dict(self.data, playlist_title='')
        with patch.object(self.ddb, 'getPlaylistVideos', return_value=stale), \
                patch.object(self.yt, 'ytapi_search_playlist', return_value=refreshed), \
                patch.object(self.ddb, 'registPlaylistVideos') as save:
            result = self.handler.getVideoURL(PLAYLIST_ID)
        self.assertEqual(result['playlist_title'], '')
        self.assertEqual(save.call_args.args[0]['playlist_title'], '')

    def test_invalid_ids_do_not_touch_database(self):
        for value in (None, '', 'bad', '../playlist', 123, 'A' * 101):
            with self.subTest(value=value), patch.object(self.ddb, 'getPlaylistVideos') as get:
                result = self.handler.main({'pathParameters': {'playlist_id': value}}, None)
                self.assertEqual(result['statusCode'], 400)
                get.assert_not_called()
        self.assertEqual(self.handler.main({'pathParameters': None}, None)['statusCode'], 400)

    def test_http_response_roundtrips_name_without_headers(self):
        with patch.object(self.handler, 'getVideoURL', return_value=dict(self.data['videos'], playlist_title=self.data['playlist_title'])):
            result = self.handler.main({'pathParameters': {'playlist_id': PLAYLIST_ID}}, None)
        self.assertEqual(result['statusCode'], 200)
        self.assertEqual(json.loads(result['body'])['playlist_title'], self.data['playlist_title'])

    def test_list_errors_have_non_success_status(self):
        for status, reason, expected in ((404, 'playlistNotFound', 404), (403, 'playlistForbidden', 403), (403, 'quotaExceeded', 503), (503, 'backendError', 503)):
            with self.subTest(status=status, reason=reason), \
                    patch.object(self.handler, 'getVideoURL', side_effect=HttpError(status, reason)):
                result = self.handler.main({'pathParameters': {'playlist_id': PLAYLIST_ID}}, None)
                self.assertEqual(result['statusCode'], expected)

    def test_transport_failure_is_service_unavailable(self):
        with patch.object(self.handler, 'getVideoURL', side_effect=OSError('timeout')):
            result = self.handler.main({'pathParameters': {'playlist_id': PLAYLIST_ID}}, None)
        self.assertEqual(result['statusCode'], 503)

    def test_existing_video_index_uses_unchanged_arrays(self):
        for cached in (None, self.record):
            with self.subTest(cached=bool(cached)), \
                    patch.object(self.ddb, 'getPlaylistVideos', return_value=cached), \
                    patch.object(self.yt, 'ytapi_search_playlist', return_value=self.data), \
                    patch.object(self.ddb, 'registPlaylistVideos'):
                self.assertEqual(self.video.getVideoURL(PLAYLIST_ID, 1), (self.data['videos']['urls'][1], 'B'))

    def test_continuous_registration_accepts_extended_data(self):
        with patch.object(self.ddb, 'is_exist_continuous_playlist_id', return_value=None), \
                patch.object(self.yt, 'ytapi_search_playlist', return_value=self.data), \
                patch.object(self.ddb, 'regist_continuous_playlist_video_list') as save:
            self.continuous.main({'playlist_id': PLAYLIST_ID, 'register_id': 'test'}, None)
        self.assertEqual(save.call_args.args[0]['videos'], self.data['videos'])


if __name__ == '__main__':
    unittest.main()
