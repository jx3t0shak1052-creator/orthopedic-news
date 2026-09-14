"""
整形外科論文ニュース取得スクリプト
GitHub Actions から実行される。ANTHROPIC_API_KEY 環境変数が必要。
"""
import anthropic
import json
import os
import re
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))
today = datetime.now(JST).strftime("%Y年%m月%d日")

client = anthropic.Anthropic()

print(f"📅 {today} の論文を取得中...")

message = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=2000,
    system=(
        "あなたは整形外科の研究アシスタントです。"
        "最新の整形外科文献から8件の論文サマリーをJSON配列のみで返してください"
        "（肩は2件、脊椎・肘・手指・股関節・膝・外傷は各1件）。"
        "各オブジェクトのフィールド: "
        "specialty（脊椎/肩/肘/手指/股関節/膝/外傷のいずれか必須）, "
        "title（日本語タイトル）, "
        "journal（雑誌名と掲載年月）, "
        "overview（研究概要2〜3文）, "
        "results（主な結果2〜3文）, "
        "conclusion（結論と臨床的考察2〜3文）。"
        "JSONのみを返し、前置きや説明文は絶対に含めないこと。"
    ),
    messages=[{
        "role": "user",
        "content": (
            f"今日{today}の最新整形外科論文を各分野から"
            "（肩は2件、それ以外各1件）紹介してください。"
            "できるだけ2025〜2026年の論文を選んでください。"
            "脊椎・肩・肘・手指・股関節・膝・外傷の7分野を必ず網羅してください。"
        )
    }]
)

text = message.content[0].text
m = re.search(r'\[[\s\S]*\]', text)
if not m:
    raise ValueError("APIレスポンスからJSONが見つかりません:\n" + text[:500])

papers = json.loads(m.group(0))

# IDと日付を付与
date_str = datetime.now(JST).strftime("%Y%m%d")
for i, p in enumerate(papers):
    p["id"] = f"auto_{date_str}_{i}"
    p["isNew"] = True

output = {
    "updated": today,
    "updated_iso": datetime.now(JST).isoformat(),
    "papers": papers
}

with open("news.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"✅ {len(papers)}件の論文を news.json に保存しました")
for p in papers:
    print(f"  [{p.get('specialty','')}] {p.get('title','')[:40]}...")
