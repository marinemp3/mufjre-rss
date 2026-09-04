#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from datetime import datetime, timezone, timedelta
import os
import sys
import json
import traceback

# GitHub Actions環境では詳細なログを出力
def debug_log(msg):
    print(f"[DEBUG] {msg}", flush=True)
    # ファイルにもログを出力
    with open('debug.log', 'a', encoding='utf-8') as f:
        f.write(f"{datetime.now()}: {msg}\n")

try:
    debug_log("=== スクリプト開始 ===")
    debug_log(f"Pythonバージョン: {sys.version}")
    debug_log(f"カレントディレクトリ: {os.getcwd()}")
    debug_log(f"環境変数: {dict(os.environ)}")
    
    # ファイル一覧を出力
    debug_log("ファイル一覧:")
    for file in os.listdir('.'):
        debug_log(f"  - {file}")
    
    # SSL警告を無効化（GitHub Actions環境対応）
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    # JSTタイムゾーン
    JST = timezone(timedelta(hours=9))
    
    def fetch_page_with_retry(url, max_retries=5):
        """GitHub Actions環境向けにリトライ回数を増やしたバージョン"""
        debug_log(f"ページ取得開始: {url}")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
        }
        
        for attempt in range(max_retries):
            try:
                debug_log(f"試行 {attempt + 1}/{max_retries}")
                
                # GitHub Actions環境ではより長いタイムアウトを設定
                response = requests.get(
                    url,
                    headers=headers,
                    timeout=60,  # タイムアウトを延長
                    verify=False,
                    allow_redirects=True
                )
                
                debug_log(f"ステータスコード: {response.status_code}")
                debug_log(f"レスポンスヘッダー: {dict(response.headers)}")
                
                response.raise_for_status()
                
                # コンテンツのエンコーディングを処理
                if response.encoding is None:
                    response.encoding = 'utf-8'
                
                content = response.text
                debug_log(f"コンテンツサイズ: {len(content)} bytes")
                debug_log(f"コンテンツの最初の200文字: {content[:200]}")
                
                # コンテンツをファイルに保存（デバッグ用）
                with open('fetched_content.html', 'w', encoding='utf-8') as f:
                    f.write(content)
                debug_log("fetched_content.html に保存しました")
                
                return content
                
            except requests.exceptions.Timeout as e:
                debug_log(f"タイムアウトエラー (試行 {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    import time
                    wait_time = 2 ** attempt
                    debug_log(f"{wait_time}秒待機して再試行")
                    time.sleep(wait_time)
                else:
                    debug_log("全ての試行がタイムアウトしました")
                    
            except requests.exceptions.SSLError as e:
                debug_log(f"SSLエラー (試行 {attempt + 1}): {e}")
                # SSLエラーの場合は即座に次の試行へ
                if attempt < max_retries - 1:
                    import time
                    time.sleep(1)
                else:
                    debug_log("全ての試行でSSLエラーが発生")
                    
            except requests.exceptions.RequestException as e:
                debug_log(f"リクエストエラー (試行 {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    import time
                    wait_time = 2 ** attempt
                    debug_log(f"{wait_time}秒待機して再試行")
                    time.sleep(wait_time)
                else:
                    debug_log("全ての試行が失敗")
        
        debug_log("ページ取得に失敗しました")
        return None
    
    def extract_articles(html_content):
        """HTMLから記事を抽出（より堅牢なバージョン）"""
        debug_log("記事抽出開始")
        
        if not html_content:
            debug_log("HTMLコンテンツが空です")
            return []
        
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            debug_log("BeautifulSoupでパース完了")
        except Exception as e:
            debug_log(f"BeautifulSoupパースエラー: {e}")
            # lxmlが使えない場合のフォールバック
            try:
                soup = BeautifulSoup(html_content, 'html5lib')
                debug_log("html5libでパース完了")
            except:
                soup = BeautifulSoup(html_content, 'html.parser')
                debug_log("デフォルトパーサーでパース完了")
        
        articles = []
        
        # 複数のセレクタを試行
        selectors = [
            'li.c-media_list-item',
            '.c-media_list-item',
            'article.c-media_list-item',
            '.m-list-media'
        ]
        
        items = []
        for selector in selectors:
            items = soup.select(selector)
            if items:
                debug_log(f"セレクタ '{selector}' で {len(items)} 件見つかりました")
                break
        
        if not items:
            debug_log("記事が見つかりませんでした。HTML構造を調査します。")
            # HTMLの構造を分析
            debug_log("主な要素:")
            for tag in ['h1', 'h2', 'h3', 'div', 'article']:
                elems = soup.find_all(tag)
                if elems:
                    debug_log(f"  {tag}: {len(elems)}件")
            
            # クラス名を分析
            classes = set()
            for elem in soup.find_all(class_=True):
                classes.update(elem.get('class', []))
            debug_log(f"クラス名: {sorted(list(classes))[:20]}")
            
            return articles
        
        debug_log(f"{len(items)}件の記事アイテムを処理します")
        
        for idx, item in enumerate(items, 1):
            try:
                debug_log(f"記事 {idx} を処理中...")
                article = {'tags': []}
                
                # タイトルとリンク（複数のセレクタを試行）
                title_selectors = [
                    '.m-list-media_list-item_title a',
                    '.a-text-link',
                    'h2 a',
                    'h3 a',
                    'a'
                ]
                
                link_elem = None
                for selector in title_selectors:
                    link_elem = item.select_one(selector)
                    if link_elem and link_elem.get_text(strip=True):
                        debug_log(f"  タイトル発見 (セレクタ: {selector})")
                        break
                
                if not link_elem:
                    debug_log(f"  記事 {idx}: タイトルが見つかりません")
                    continue
                
                title = link_elem.get_text(strip=True)
                link = link_elem.get('href')
                
                if not title or not link:
                    debug_log(f"  記事 {idx}: タイトルまたはリンクが空です")
                    continue
                
                # 絶対URLに変換
                if link.startswith('/'):
                    link = 'https://www.murc.jp' + link
                elif not link.startswith('http'):
                    link = 'https://www.murc.jp/' + link.lstrip('/')
                
                # 日付
                date_elem = item.select_one('.m-list-media_info_date')
                date = date_elem.get_text(strip=True) if date_elem else ''
                
                # タグ
                tag_elems = item.select('.a-parts-badge')
                tags = [tag.get_text(strip=True) for tag in tag_elems if tag.get_text(strip=True)]
                
                article = {
                    'title': title,
                    'link': link,
                    'date': date,
                    'tags': tags
                }
                
                articles.append(article)
                debug_log(f"  [ステッカー] 記事抽出: {title[:50]}...")
                
            except Exception as e:
                debug_log(f"  記事 {idx} の抽出中にエラー: {e}")
                continue
        
        debug_log(f"抽出完了: {len(articles)}件の記事")
        
        # 抽出した記事のサマリーを出力
        if articles:
            debug_log("抽出した記事のサマリー:")
            for i, article in enumerate(articles[:5], 1):
                debug_log(f"  {i}. {article['title'][:40]}... ({article['date']})")
        else:
            debug_log("[ステッカー] 記事が1件も抽出されていません")
        
        return articles
    
    def generate_rss(articles, output_path):
        """RSSフィードを生成"""
        debug_log(f"RSS生成開始: {output_path}")
        
        if not articles:
            debug_log("[ステッカー] 記事が0件のため、空のRSSを生成します")
        
        fg = FeedGenerator()
        fg.title('MURC 中国関連レポート・コラム')
        fg.description('三菱UFJリサーチ&コンサルティングの中国関連レポート・コラム一覧（自動生成）')
        fg.link(href='https://www.murc.jp/library/tags/tag_564/', rel='alternate')
        fg.language('ja')
        
        now = datetime.now(JST)
        fg.lastBuildDate(now)
        fg.pubDate(now)
        
        for article in articles:
            entry = fg.add_entry()
            entry.title(article.get('title', 'タイトルなし'))
            
            if article.get('link'):
                entry.link(href=article['link'])
                entry.guid(article['link'], permalink=True)
            else:
                entry.guid(f"murc-{datetime.now().timestamp()}", permalink=False)
            
            if article.get('date'):
                try:
                    pub_date = datetime.strptime(article['date'], "%Y/%m/%d").replace(tzinfo=JST)
                    entry.pubDate(pub_date)
                except:
                    entry.pubDate(now)
            
            if article.get('tags'):
                for tag in article['tags']:
                    if tag:
                        entry.category(term=tag)
                entry.description(f"カテゴリ: {', '.join(article['tags'])}")
            else:
                entry.description('MURC中国関連レポート')
        
        try:
            # RSSファイルを出力
            rss_str = fg.rss_str(pretty=True)
            with open(output_path, 'wb') as f:
                f.write(rss_str)
            debug_log(f"[ステッカー] RSS生成完了: {output_path} ({len(articles)}件)")
            
            # 生成されたファイルの確認
            if os.path.exists(output_path):
                file_size = os.path.getsize(output_path)
                debug_log(f"ファイルサイズ: {file_size} bytes")
                with open(output_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    debug_log(f"RSSの最初の200文字: {content[:200]}")
            else:
                debug_log("[ステッカー] ファイルが作成されていません")
                
        except Exception as e:
            debug_log(f"RSSファイル出力エラー: {e}")
            raise
    
    # ===== メイン実行 =====
    debug_log("=== メイン処理開始 ===")
    
    url = 'https://www.murc.jp/library/tags/tag_564/'
    output_path = os.environ.get('RSS_OUTPUT_PATH', 'feed.xml')
    
    debug_log(f"ターゲットURL: {url}")
    debug_log(f"出力パス: {output_path}")
    
    # ページ取得
    html_content = fetch_page_with_retry(url)
    
    if html_content:
        debug_log("ページ取得成功")
        articles = extract_articles(html_content)
        generate_rss(articles, output_path)
        debug_log("=== スクリプト正常終了 ===")
    else:
        debug_log("[ステッカー] ページ取得失敗 - 空のRSSを生成")
        generate_rss([], output_path)
        debug_log("=== スクリプト終了（空のRSS生成） ===")
        sys.exit(1)
    
    # 最終確認
    debug_log("最終ファイル一覧:")
    for file in os.listdir('.'):
        size = os.path.getsize(file) if os.path.isfile(file) else 'DIR'
        debug_log(f"  {file} ({size})")

except Exception as e:
    debug_log(f"[ステッカー] 致命的エラー: {e}")
    debug_log(traceback.format_exc())
    
    # エラー時でも空のRSSを生成する試み
    try:
        debug_log("エラーリカバリ: 空のRSSを生成")
        fg = FeedGenerator()
        fg.title('MURC 中国関連レポート・コラム (エラーリカバリ)')
        fg.link(href='https://www.murc.jp/library/tags/tag_564/', rel='alternate')
        fg.language('ja')
        fg.lastBuildDate(datetime.now(JST))
        
        output_path = os.environ.get('RSS_OUTPUT_PATH', 'feed.xml')
        fg.rss_file(output_path)
        debug_log(f"[ステッカー] 空のRSSを生成: {output_path}")
    except:
        debug_log("空のRSS生成にも失敗")
    
    sys.exit(1)
