# API Gatewayのリクエスト解析・レスポンス生成
import json
import os

QUEST_UA = 'stagefright'
PC_AE = 'identity'  # 'Accept-Encoding': 'identity'
LOADER_UA = 'UnityPlayer'  # StringLoader

CORS = {"Access-Control-Allow-Origin": "*"}

# 動画リストの取得件数 (?limit=)
LIMIT_STEP = 50  # YouTube APIの1ページ
MAX_LIMIT = 500


def headers(event):
    return event.get('headers') or {}


def query_params(event):
    return event.get('queryStringParameters') or {}


def path_param(event, name):
    value = (event.get('pathParameters') or {}).get(name)
    if not isinstance(value, str):
        return None
    return value.strip() or None


def parse_index(value):
    # 不正値・負数はNone
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n >= 0 else None


def parse_limit(event):
    # 50刻みに切り上げて50〜500に収める。省略・不正値は50
    try:
        n = int(query_params(event).get('limit', LIMIT_STEP))
    except (TypeError, ValueError):
        return LIMIT_STEP
    n = -(-n // LIMIT_STEP) * LIMIT_STEP
    return min(max(n, LIMIT_STEP), MAX_LIMIT)


def client_type(event):
    # 'quest' | 'pc' | 'other'(YTTL・StringLoaderなど)
    h = headers(event)
    ua = h.get('User-Agent', '')
    ae = h.get('Accept-Encoding', '')
    print('User-Agent:', ua)
    print('Accept-Encoding:', ae)
    if QUEST_UA in ua:
        return 'quest'
    if ae == PC_AE:
        return 'pc'
    return 'other'


def is_loader(event):
    return LOADER_UA in headers(event).get('User-Agent', '')


def cf_domain():
    return os.environ.get('CF_DOMAIN', '')


def not_found_url():
    return f'{cf_domain()}/nf.mp4'


def redirect(url):
    return {
        'headers': {
            "Content-type": "text/html; charset=utf-8",
            **CORS,
            "location": url
        },
        'statusCode': 302,
        'body': "",
    }


def title_json(title):
    # YTTL向け
    return {
        'headers': {
            "Content-type": "text/html; charset=utf-8",
            **CORS,
        },
        'statusCode': 200,
        'body': json.dumps({'title': title}, ensure_ascii=False),
    }


def video_response(event, url, title):
    # VRCプレイヤー(Quest/PC)は動画へリダイレクト、それ以外はタイトルを返却
    kind = client_type(event)
    print('client:', kind)
    if kind == 'other':
        return title_json(title)
    return redirect(url)


def text(body, status=200):
    return {
        'headers': {
            "Content-Type": "text/plain; charset=utf-8",
            **CORS
        },
        'statusCode': status,
        'body': body,
    }


def json_text(obj, status=200):
    return text(json.dumps(obj, ensure_ascii=False), status)


def json_body(obj, status=200):
    return {
        'headers': dict(CORS),
        'statusCode': status,
        'body': json.dumps(obj),
    }


def bad_request(error='bad request'):
    return json_body({'result': 'NG', 'error': error}, 400)
