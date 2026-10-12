"""
整形外科論文ニュース取得スクリプト（PubMed 連携版 + アーカイブ対応）
================================================================
【本版の方針】
  1) まず PubMed 収載文献を実検索して「実在する論文」を確定させる
     - 主経路   : Europe PMC REST API（PubMed 収載分 = SRC:MED を対象）
     - 副経路   : NCBI E-utilities (esearch + efetch)
     - SEARCH_BACKEND 環境変数で auto / europepmc / pubmed を切替可能
  2) 取得した抄録(abstract)だけを根拠に Gemini へ日本語要約を作らせる
  3) 引用数（citedByCount）を選定スコアに加味し、注目度の高い論文を優先
  4) 取得した論文を archive.json に累積保存（日付・分野・PMID 付き）

【出力ファイル】
  news.json    : 直近7件（当日分）
  details.json : 詳細解析の累積キャッシュ
  archive.json : 過去に取得した全論文の累積アーカイブ

【環境変数】
  GOOGLE_API_KEY : Gemini API キー（必須。--dry-run 時は不要）
  NCBI_API_KEY   : NCBI E-utilities 用キー（任意）
  NCBI_EMAIL     : NCBI 推奨の連絡先（任意）
  SEARCH_BACKEND : auto（既定） / europepmc / pubmed

【使い方】
  python fetch_news.py             # 通常実行
  python fetch_news.py --dry-run   # 検索のみ。書き込みせず結果を表示
"""
import json, os, re, sys, time, random, html
import urllib.parse, urllib.request, urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))
NOW = datetime.now(JST)
