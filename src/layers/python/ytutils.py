import urllib.request
import xml.etree.ElementTree as ET


def getRSS(channel_id):
    url = "https://www.youtube.com/feeds/videos.xml?channel_id="+channel_id
    body = getRssFeed(url)
    root = ET.fromstring(body)
    if len(root) == 0:
        return [], False
    return root, True


def getRssFeed(url):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as res:
        body = res.read().decode('utf-8')
    return body


def scrapingRSS(rssdata):
    descriptions = []
    urls = []
    name = ""
    for child in rssdata:
        if child.tag == '{http://www.w3.org/2005/Atom}author':
            for author in child:
                if author.tag == '{http://www.w3.org/2005/Atom}name':
                    name = child.find('{http://www.w3.org/2005/Atom}name').text
        if child.tag == '{http://www.w3.org/2005/Atom}entry':
            for childchild in child:
                if childchild.tag == '{http://www.w3.org/2005/Atom}title':
                    descriptions.append(child.find(
                        '{http://www.w3.org/2005/Atom}title').text)
                if childchild.tag == '{http://www.w3.org/2005/Atom}link':
                    urls.append(childchild.attrib['href'])
    return name, urls, descriptions
