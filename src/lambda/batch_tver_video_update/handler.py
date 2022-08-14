import os
import urllib.request
import time
import boto3
from bs4 import BeautifulSoup


dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['VRC_VIDEO_TABLE'])

tverurl = 'https://tver.jp'


def main(event, context):
    start = time.time()

    registTVer('ranking')
    registTVer('drama')
    registTVer('variety')
    registTVer('documentary')
    registTVer('anime')
    registTVer('sport')
    registTVer('other')
    registTVer('c')

    registTVer('short')

    registTVer('area-kanto', 'special/')
    registTVer('area-kansai', 'special/')
    registTVer('area-chubu', 'special/')
    registTVer('area-hokkaido-tohoku', 'special/')
    registTVer('area-chugoku-shikoku', 'special/')
    registTVer('area-kyusyu-okinawa', 'special/')

    elapsed_time = time.time() - start
    print('{0}'.format(elapsed_time) + '[sec]')


def updateDB(attribute, urls, titles):
    table.put_item(
        Item={
            'user_id': 'tver',
            'video_id': attribute,
            'urls': urls,
            'titles': titles
        }
    )


def getHTML(url):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as res:
        body = res.read().decode('utf-8')
    return body


def registTVer(attribute, urlprefix=''):
    print('registTVer:' + attribute)
    try:
        html = getHTML(f'https://tver.jp/{urlprefix}{attribute}')
    except urllib.error.URLError as e:
        print(e.reason)
        return
    soup = BeautifulSoup(html, "html.parser")
    urls = []
    titles = []
    for lielements in soup.select('.resumable'):
        title = lielements.find('h3').text
        subtitle = lielements.find('p', class_='summary').text
        url = lielements.find('a', class_='detail_link').get('href')
        print('タイトル:'+title + subtitle)
        print('URL:'+url)
        urls.append(f'{tverurl}{url}')
        titles.append(f'{title} / {subtitle}')
    updateDB(attribute, urls, titles)
