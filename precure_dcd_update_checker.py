#!/usr/bin/env python3
import time
import datetime
from dateutil.parser import parse
import re
from pprint import pprint
import argparse
from io import BytesIO
import requests
from bs4 import BeautifulSoup
from twython import Twython, TwythonError
from pymongo.mongo_client import MongoClient

DOMAIN = 'http://www.precure-live.com'
URL_BASE = DOMAIN + '/mp/'

def tweet_news():
    '''ニュースの更新を確認してツイートする関数'''
    # init
    topics = MongoClient().precure_magicalparty.topics
    t = get_twython()

    # indexページの取得
    r = requests.get(URL_BASE)
    r.encoding = 'euc-ja'
    soup = BeautifulSoup(r.text)
     
    # ニュース一覧の取得
    dds = soup.select('.dl-topics dd')
    new_topics = []
     
    # 更新日を取得
    date = parse(dds[0].find_previous().text)

    # 各トピックスを処理
    for dd in dds:

        # ニュースがデータベース内にあれば終了
        if topics.find({'_id': date}).count():
            break
        
        # 追加するトピックスを更新日のものに限定 = 区切り線が来たらそこで切る
        if dd.has_attr('class') and dd['class'][0] == 'line':
            break

        # aタグが存在しないddタグはスキップ
        if not dd.a:
            continue

        # 新しいトピック辞書の作成
        topic = {}
        a = dd.a
        topic['category'] = a['class']
        topic['category_text'] = a.text
        if not a['href'].startswith('http'):
            topic['url'] = DOMAIN + a['href']
        else:
            topic['url'] = a['href']
        
        # トピックスのタイトルを取得
        r = requests.get(topic['url'])
        print(topic['url'])
        r.encoding = 'euc-ja'
        soup = BeautifulSoup(r.text)
        topic['title'] = soup.h3.img['alt']

        new_topics.append(topic)

    # 各トピックについて、
    for topic in new_topics:
        # 1. データベースを更新
        topics.update({'_id': date}, {'topics': new_topics}, upsert=True)

        # 2. ツイート
        status = '「{category}」が更新されたモフ！ / {title} - {url}'.format(category=topic['category_text'], title=topic['title'], url=topic['url'])
        t.update_status(status=status)
        
def get_twython():
    '''twythonオブジェクトを取得する関数'''
    if args.debug:
        with open('.credentials_sakuramochi_pre') as f:
            app_key, app_secret, oauth_token, oauth_secret = [x.strip() for x in f]
    else:
        with open('.credentials') as f:
            app_key, app_secret, oauth_token, oauth_secret = [x.strip() for x in f]
    t = Twython(app_key, app_secret, oauth_token, oauth_secret)
    return t

def get_soup(url):
    '''指定したurlのsoupを返す関数'''
    r = requests.get(url)
    soup = BeautifulSoup(r.text)
    return soup
    
def update_cards():
    '''cardsデータベースを更新し、新しいカードをツイートする関数'''
    cards = MongoClient().precure_magicalparty.cards
    urls = get_urls()
    for url in urls:
        cards_soup = get_cards(url)
        for card_soup in cards_soup:
            card = make_card(card_soup)
            res = cards.update({'_id': card['_id']}, card, upsert=True)
            # 新しいカードが追加された時にツイートする
            if not res['updatedExisting']:
                ok = tweet_new_card(card, url_base + url)
                if ok:
                    cards.update({'_id': card['_id']}, {'$set': {'tweeted': True}})
                    time.sleep(1)

def parse_card_number(number):
    '''.card-number で取得したデータをパースする関数

    次のフォーマットに対応:
    - PP01 01/51
    - PPプロモ0-5
    - PPプロモ01
    '''
    # パタン: PP01 01/51
    m = re.match(r'(.+)\s+(\d+)/(\d+)', number)
    if m:
        return m.groups()

    # パタン: PPプロモ0-5
    m = re.match(r'(.+)-(\d+)', number)
    if m:
        return tuple(list(m.groups()) + [None])

    # パタン: PPプロモ01
    m = re.match(r'(.+?)(\d+)', number)
    if m:
        return tuple(list(m.groups()) + [None])
    
def get_urls():
    '''各シリーズのページURLを取得する関数'''
    r = requests.get(URL_BASE + 'cardlist/')
    r.encoding = 'euc-ja'
    soup = BeautifulSoup(r.text)
    urls = [i['href'] for i in soup.select('#snavi li a')[:-1]]
    return urls

def get_cards(url):
    '''ページのURLからカードリストのsoupを作る関数'''
    r = requests.get(URL_BASE + url)
    r.encoding = 'euc-ja'
    soup = BeautifulSoup(r.text)
    cards = soup.select('.cardCol')
    return cards

def make_card(card_soup):
    '''1枚のカードのsoupからcardオブジェクトを作成する関数'''
    card = dict()
    card['series_name'] = card_soup.select('.card-title')[0].text.strip()
    number = card_soup.select('.card-number')[0].text.strip()
    card['series'], card['number'], card['number_max'] = parse_card_number(number)
    card['_id'] = '{}-{}'.format(card['series'], card['number'])
    card['name'] = card_soup.select('.card-name')[0].text.strip()
    card['character'] = card_soup.select('.card-character')[0].text.strip().replace('　', ' ')
    card['front_img_url'] = url_base + card_soup.select('.card-img')[0].img['src'].strip()
    card['back_img_url'] = url_base + card_soup.select('.card-img')[1].img['src'].strip()
    card['type'] = card_get_img_alt(card_soup, '.card-kind dd')
    card['rarity'] = card_get_img_alt(card_soup, '.card-rare dd')
    card['mark'] = card_get_img_alt(card_soup, '.card-mark dd')
    card['color'] = card_get_img_alt(card_soup, '.card-color dd')
    card['rank'] = card_get_img_alt(card_soup, '.card-rank dd')
    card['tweeted'] = False
    if args.debug:
        pprint(card)
        print('-' * 4)
    return card

def card_get_img_alt(soup, selector):
    '''セレクタに含まれている最初のimgのaltを取得する関数'''
    try:
        return soup.select(selector)[0].img['alt'].strip()
    except:
        return None

def tweet_new_card(card, cardlist_url):
    '''新しいカードを画像付きでツイートする関数'''
    t = get_twython()
    media_ids = []
    urls = [card['front_img_url'], card['back_img_url']]
    for url in urls:
        img = BytesIO(requests.get(url).content)
        r = t.upload_media(media=img)
        media_ids.append(r['media_id'])

    # ツイートテキストを用意
    status = '''{} / {} / {}{}
{}
{}
{}
{}'''.format(card['_id'], card['type'], card['rarity'], card['rank'], card['series_name'], card['character'], card['name'], cardlist_url)
    
    if args.debug:
        print(len(status), status)
        print('media_ids:', media_ids)
        print('-' * 4)
    
    try:
        t.update_status(status=status, media_ids=media_ids)
        return True
    except TwythonError:
        # 文字数がオーバーしていたと仮定して、その場合にはシリーズ名の後半を削る
        status = '''{} / {} / {}{}
{}
{}
{}
{}'''.format(card['_id'], card['type'], card['rarity'], card['rank'], card['series_name'].split()[0], card['character'], card['name'], cardlist_url)
        if args.debug:
            print('2nd attempt:')
            print(len(status), status)
            print('media_ids:', media_ids)
            print('-' * 4)
        try:
            t.update_status(status=status, media_ids=media_ids)
            return True
        except TwythonError as e:
            print('id:', card['_id'])
            print('TwythonError:', e)
            return False

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['tweet_news', 'update_cards'])
    parser.add_argument('--debug', '-d', action='store_true')
    args = parser.parse_args()
    if args.action == 'tweet_news':
        tweet_news()
    elif args.action == 'update_cards':
        update_cards()

