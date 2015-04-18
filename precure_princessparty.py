#!/usr/bin/env python3
import datetime
from dateutil.parser import parse
import requests
from bs4 import BeautifulSoup
from twython import Twython
from pymongo.mongo_client import MongoClient

def main():

    # init
    topics = MongoClient().precure_princessparty.topics
    t = get_twython()

    # indexページの取得
    DOMAIN = 'http://www.precure-live.com'
    URL_BASE = DOMAIN + '/pp/'
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
        topic['url'] = DOMAIN + a['href']
        
        # トピックスのタイトルを取得
        r = requests.get(topic['url'])
        r.encoding = 'euc-ja'
        soup = BeautifulSoup(r.text)
        topic['title'] = soup.h3.img['alt']

        new_topics.append(topic)

    # 各トピックについて、
    for topic in new_topics:
        # 1. データベースを更新
        topics.update({'_id': date}, {'topics': new_topics}, upsert=True)

        # 2. ツイート
        status = '「{category}」のページが更新されました！ / {title} - {url}'.format(category=topic['category_text'], title=topic['title'], url=topic['url'])
        print(status)
        t.update_status(status=status)
        
def get_twython():
    '''
    authonticated the account and return twitter class
    '''
    # read app credentials
    with open('.credentials') as f:
        app_key, app_secret, oauth_token, oauth_secret = [x.strip() for x in f]
    t = Twython(app_key, app_secret, oauth_token, oauth_secret)
    return t

if __name__ == '__main__':
    main()

