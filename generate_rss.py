#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from datetime import datetime, timezone, timedelta
import os
import sys
import traceback

# エラーログをファイルに出力
def log_error(msg):
    with open('error.log', 'a', encoding='utf-8') as f:
        f.write(f"{datetime.now()}: {msg}\n")
    print(msg)

try:
    # JSTタイムゾーン
    JST = timezone(timedelta(hours=9))
    
    print("スクリプトを開始します...")
    
    # SSL警告を無効化
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    def fetch_page(url):
        print(f"ページを取得中: {url}")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=30, verify=False)
            response.raise_for_status()
            print(f"✅ ページ取得成功: {response.status_code}")
            return response.text
        except Exception as e:
            log_error(f"ページ取得エラー: {e}")
            return None
    
    def extract_articles(html):
        print("記事を抽出中...")
        soup = BeautifulSoup(html, 'html.parser')
        articles = []
        
        # 全ての記事アイテムを検索
        items = soup.select('li.c-media_list-item')
        print(f"見つかった記事数: {len(items)}")
        
        for item in items:
            try:
                # タイトルとリンク
                link_elem = item.select_one('.m-list-media_list-item_title a')
                if not link_elem:
                    continue
                
                title = link_elem.get_text(strip=True)
                link = link_elem.get('href')
                if link and link.startswith('/'):
                    link = 'https://www.murc.jp' + link
                
                # 日付
                date_elem = item.select_one('.m-list-media_info_date')
                date = date_elem.get_text(strip=True) if date_elem else ''
                
                articles.append({
                    'title': title,
                    'link': link,
                    'date': date,
                    'tags': []
                })
                print(f"  ✓ 記事: {title[:30]}...")
            except Exception as e:
                log_error(f"記事抽出エラー: {e}")
                continue
        
        return articles
    
    def generate_rss(articles, output_path):
        print(f"RSS生成中: {output_path}")
        fg = FeedGenerator()
        fg.title('MURC 中国関連レポート・コラム')
        fg.description('自動生成RSSフィード')
        fg.link(href='https://www.murc.jp/library/tags/tag_564/', rel='alternate')
        fg.language('ja')
        fg.lastBuildDate(datetime.now(JST))
        
        for article in articles:
            entry = fg.add_entry()
            entry.title(article['title'])
            entry.link(href=article['link'])
            
            if article['date']:
                try:
                    pub_date = datetime.strptime(article['date'], "%Y/%m/%d").replace(tzinfo=JST)
                    entry.pubDate(pub_date)
                except:
                    pass
            
            entry.description('MURC中国関連レポート')
        
        fg.rss_file(output_path)
        print(f"✅ RSS生成完了: {output_path}")
        print(f"記事数: {len(articles)}")
    
    # メイン実行
    url = 'https://www.murc.jp/library/tags/tag_564/'
    output = os.environ.get('RSS_OUTPUT_PATH', 'feed.xml')
    
    html = fetch_page(url)
    if html:
        articles = extract_articles(html)
        generate_rss(articles, output)
        print("✅ 処理完了")
    else:
        log_error("HTML取得失敗")
        # 空のRSSを作成
        generate_rss([], output)
        print("⚠ 空のRSSを作成しました")
        
except Exception as e:
    log_error(f"致命的エラー: {e}")
    traceback.print_exc()
    sys.exit(1)
