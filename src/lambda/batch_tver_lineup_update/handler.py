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

    registTVer2('lineup')

    elapsed_time = time.time() - start
    print('{0}'.format(elapsed_time) + '[sec]')


def getHTML(url):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as res:
        body = res.read().decode('utf-8')
    return body


def registTVer2(attribute, urlprefix=''):
    print('registTVer2:' + attribute)
    try:
        html = getHTML(f'https://tver.jp/{urlprefix}{attribute}')
    except urllib.error.URLError as e:
        print(e.reason)
        return
    soup = BeautifulSoup(html, "html.parser")
    # urls = []
    # titles = []
    for lielements in soup.select('li'):
        titleElements = lielements.find('h3')
        if titleElements is None:
            continue
        title = titleElements.text
        # subtitle = lielements.find('p', class_='summary').text  # 無い
        url = lielements.find('a', class_='detail_link').get('href')
        print('タイトル:'+title)
        print('URL:'+url)
        if url == '':
            continue
        updateDB2(attribute, url, title)
    #     urls.append(f'{tverurl}{url}')
    #     titles.append(f'{title}')
    # updateDB(attribute, urls, titles)


def updateDB2(attribute, url, title):
    table.put_item(
        Item={
            'user_id': f'tver_{attribute}',
            'video_id': title,
            'url': url,
            'title': title
        }
    )
