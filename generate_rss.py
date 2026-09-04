#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from datetime import datetime, timezone, timedelta
import re
import os
import urllib3

# SSL警告を無効化（必要に応じて）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# JST (日本時間) のタイムゾーン設定
JST = timezone(timedelta(hours=9))

def fetch_page_with_retry(url, max_retries=3):
    """
    指定されたURLからHTMLを取得（リトライ機能付き）
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    
    for attempt in range(max_retries):
        try:
            print(f"接続試行 {attempt + 1}/{max_retries}...")
            
            # SSL検証を無効にしてリクエスト（問題のある証明書に対応）
            response = requests.get(
                url, 
                headers=headers, 
                timeout=30,
                verify=False  # SSL証明書の検証をスキップ
            )
            response.raise_for_status()
            
            # エンコーディングを自動検出
            if response.encoding is None:
                response.encoding = 'utf-8'
            
            print(f"ステータスコード: {response.status_code}")
            print(f"コンテンツサイズ: {len(response.content)} bytes")
            
            return response.text
            
        except requests.exceptions.SSLError as e:
            print(f"SSLエラー発生 (試行 {attempt + 1}): {e}")
            if attempt == max_retries - 1:
                # 最終試行でSSLエラーが続く場合、別の方法を試す
                print("SSLエラーが続くため、代替方法を試みます...")
                return fetch_page_with_alternate_method(url)
                
        except requests.exceptions.RequestException as e:
            print(f"リクエストエラー (試行 {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                import time
                wait_time = 2 ** attempt  # 指数バックオフ
                print(f"{wait_time}秒待機して再試行します...")
                time.sleep(wait_time)
            else:
                print("すべての再試行が失敗しました。")
                return None
    
    return None

def fetch_page_with_alternate_method(url):
    """
    代替方法：セッションを使用して取得
    """
    try:
        session = requests.Session()
        session.verify = False
        
        # セッションにヘッダーを設定
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        
        response = session.get(url, timeout=30)
        response.raise_for_status()
        
        print(f"代替方法成功！ステータスコード: {response.status_code}")
        return response.text
        
    except Exception as e:
        print(f"代替方法も失敗: {e}")
        return None

def parse_date(date_str):
    """
    日付文字列をパースしてdatetimeオブジェクトに変換
    例: "2026/09/04" -> datetimeオブジェクト
    """
    try:
        # 「2026/09/04」形式に対応
        return datetime.strptime(date_str.strip(), "%Y/%m/%d").replace(tzinfo=JST)
    except ValueError:
        try:
            # 「2026-09-04」形式に対応
            return datetime.strptime(date_str.strip(), "%Y-%m-%d").replace(tzinfo=JST)
        except ValueError:
            try:
                # 「2026年09月04日」形式に対応
                return datetime.strptime(date_str.strip(), "%Y年%m月%d日").replace(tzinfo=JST)
            except ValueError:
                # パースできない場合は現在時刻を使用
                print(f"日付のパースに失敗: {date_str}")
                return datetime.now(JST)

def extract_articles(html_content):
    """
    HTMLから記事一覧を抽出する関数
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    articles = []
    
    # 記事リストの各アイテムを取得
    # HTMLの構造: li.c-media_list-item > div.m-list-media
    list_items = soup.select('li.c-media_list-item')
    
    if not list_items:
        print("警告: 記事が見つかりませんでした。HTML構造が変更された可能性があります。")
        print("HTMLの最初の500文字を表示:")
        print(html_content[:500])
        return articles
    
    print(f"{len(list_items)}件の記事が見つかりました。")
    
    for item in list_items:
        article = {}
        
        # 日付を取得
        date_elem = item.select_one('.m-list-media_info_date')
        if date_elem:
            article['date'] = date_elem.get_text(strip=True)
        
        # タイトルとリンクを取得
        link_elem = item.select_one('.m-list-media_list-item_title a')
        if link_elem:
            article['title'] = link_elem.get_text(strip=True)
            article['link'] = link_elem.get('href')
            # 相対URLを絶対URLに変換
            if article['link'] and article['link'].startswith('/'):
                article['link'] = 'https://www.murc.jp' + article['link']
        else:
            # 代替セレクタを試す
            link_elem = item.select_one('a.a-text-link')
            if link_elem:
                article['title'] = link_elem.get_text(strip=True)
                article['link'] = link_elem.get('href')
                if article['link'] and article['link'].startswith('/'):
                    article['link'] = 'https://www.murc.jp' + article['link']
        
        # タグ（カテゴリ）を取得
        tags = []
        # 複数のセレクタを試す
        badge_selectors = [
            '.c-badge-item .a-parts-badge',
            '.c-badge .a-parts-badge',
            '.m-list-media_list-item_badge .a-parts-badge'
        ]
        
        for selector in badge_selectors:
            badge_items = item.select(selector)
            if badge_items:
                for badge in badge_items:
                    tag_text = badge.get_text(strip=True)
                    if tag_text and tag_text not in tags:
                        tags.append(tag_text)
                break
        
        article['tags'] = tags
        
        # 記事が有効なデータを持っている場合のみ追加
        if article.get('title') and article.get('link'):
            articles.append(article)
            print(f"記事を抽出: {article['title'][:50]}...")
    
    return articles

def generate_rss(articles, output_path='feed.xml'):
    """
    記事データからRSSフィードを生成
    """
    if not articles:
        print("警告: 記事が1件もありません。空のRSSフィードを生成します。")
    
    fg = FeedGenerator()
    
    # フィード全体の情報設定
    fg.title('MURC 中国関連レポート・コラム')
    fg.description('三菱UFJリサーチ&コンサルティングの中国関連レポート・コラム一覧（自動生成RSS）')
    fg.link(href='https://www.murc.jp/library/tags/tag_564/', rel='alternate')
    fg.language('ja')
    
    # 現在時刻を最終更新日時に設定
    now = datetime.now(JST)
    fg.lastBuildDate(now)
    fg.pubDate(now)
    
    # 各記事をフィードに追加
    for article in articles:
        entry = fg.add_entry()
        
        # タイトル
        entry.title(article.get('title', 'タイトルなし'))
        
        # リンク
        if article.get('link'):
            entry.link(href=article['link'])
        
        # 日付（パースしてRSS用にフォーマット）
        if article.get('date'):
            pub_date = parse_date(article['date'])
            entry.pubDate(pub_date)
        
        # カテゴリ（タグ）
        for tag in article.get('tags', []):
            if tag:
                entry.category(term=tag)
        
        # GUID（一意な識別子）- リンクがない場合はタイトルと日付で代用
        if article.get('link'):
            entry.guid(article['link'], permalink=True)
        else:
            guid_text = f"{article.get('title', '')}-{article.get('date', '')}"
            entry.guid(guid_text, permalink=False)
        
        # 説明（簡易版：タグを説明として使用）
        if article.get('tags'):
            desc = f"カテゴリ: {', '.join(article['tags'])}"
            entry.description(desc)
        else:
            entry.description('MURCの中国関連レポート・コラムです。')
    
    # RSSファイルを出力
    try:
        rss_str = fg.rss_str(pretty=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(rss_str.decode('utf-8'))
        print(f"RSSフィードを生成しました: {output_path}")
        print(f"記事数: {len(articles)}")
    except Exception as e:
        print(f"RSSファイルの出力に失敗: {e}")

def main():
    """
    メイン実行関数
    """
    # ターゲットURL
    url = 'https://www.murc.jp/library/tags/tag_564/'
    
    print(f"URLからHTMLを取得中: {url}")
    html_content = fetch_page_with_retry(url)
    
    if not html_content:
        print("HTMLの取得に失敗しました。処理を終了します。")
        # エラー時でも空のRSSを作成して、壊れないようにする
        generate_rss([], os.environ.get('RSS_OUTPUT_PATH', 'feed.xml'))
        return
    
    print("HTMLから記事を抽出中...")
    articles = extract_articles(html_content)
    
    print(f"{len(articles)}件の記事を抽出しました。")
    
    # RSSフィードを生成
    output_path = os.environ.get('RSS_OUTPUT_PATH', 'feed.xml')
    generate_rss(articles, output_path)

if __name__ == '__main__':
    main()
