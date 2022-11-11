import os
import urllib.request
import time
import boto3
from bs4 import BeautifulSoup
from selenium import webdriver

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['VRC_VIDEO_TABLE'])

tverurl = 'https://tver.jp'
# driver = webdriver.Chrome(chrome_options=options)


def main(event, context):
    start = time.time()

    registTVer('variety', 'tags/')
    registTVer('news_documentary', 'tags/')
    registTVer('anime', 'tags/')
    registTVer('drama', 'tags/')
    # registTVer('variety')
    # registTVer('documentary')
    # registTVer('anime')
    # registTVer('sport')
    # registTVer('other')
    # registTVer('c')

    # registTVer('short')

    # registTVer('area-kanto', 'special/')
    # registTVer('area-kansai', 'special/')
    # registTVer('area-chubu', 'special/')
    # registTVer('area-hokkaido-tohoku', 'special/')
    # registTVer('area-chugoku-shikoku', 'special/')
    # registTVer('area-kyusyu-okinawa', 'special/')

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
    options = webdriver.ChromeOptions()
    options.binary_location = '/opt/headless-chromium'
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--hide-scrollbars")
    options.add_argument("--single-process")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--window-size=880x996")
    options.add_argument("--no-sandbox")
    options.add_argument("--homedir=/tmp")

    driver = webdriver.Chrome(
        '/opt/chromedriver',
        options=options
    )
    driver.get(url)
    time.sleep(5)
    html = driver.page_source
    driver.quit()
    return html


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
    for div1elements in soup.find('div', class_='result-list_list__C6mde').children:
        title = div1elements.find(
            'div', class_='episode-pattern-b-layout_mainTitle__iQ_2j').text
        print(f'タイトル:::{title}')
        subtitle = div1elements.find(
            'div', class_='episode-pattern-b-layout_subTitle__BnGfu').text
        print(f'サブタイトル:::{subtitle}')
        url = div1elements.find(
            'a', class_='episode-pattern-b-layout_metaText__bndIm').get('href')
        print('URL:'+url)
        urls.append(f'{tverurl}{url}')
        titles.append(f'{title}/{subtitle}')
    updateDB(attribute, urls, titles)
