# 検索結果の動画タイトルリストを返却
import httputils
import videolist


def main(event, context):
    print('event:', event)
    params = httputils.query_params(event)
    query = params.get('q', '').strip()
    print('query:', query)
    try:
        videos = videolist.query_videos(query)
    except Exception as e:
        print('[WARN]', e)
        return httputils.json_body({'result': 'NG', 'error': 'YouTube API unavailable'}, 503)
    if params.get('version', 'v1') == 'v2':
        return httputils.json_text(videos)
    print('titles:', videos['titles'])
    return httputils.text(','.join(videos['titles']))
