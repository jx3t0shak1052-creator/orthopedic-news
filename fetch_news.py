"""
整形外科論文ニュース取得スクリプト
毎日 GitHub Actions から実行される。GOOGLE_API_KEY 環境変数が必要。
"""
import json, re, os, sys, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))
today = datetime.now(JST).strftime("%Y年%m月%d日")
KEY = os.environ.get("GOOGLE_API_KEY", "")
if not KEY:
    print("❌ GOOGLE_API_KEY が設定されていません")
    sys.exit(1)

BASE = "https://generativelanguage.googleapis.com/v1beta/models"

def call_api(url, body=None):
    """GET or POST リクエスト。レスポンスのJSONを返す"""
    if body:
        data = json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type":"application/json"})
    else:
        req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()[:300]
        raise RuntimeError(f"HTTP {e.code} {e.reason}: {body_text}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"URLError: {e.reason}")

# ─── モデル選択 ───
print("🔍 利用可能なモデルを確認中...")
model = "gemini-flash-latest"  # デフォルト
try:
    data = call_api(f"{BASE}?key={KEY}")
    all_models = [m["name"].replace("models/","") for m in data.get("models",[])]
    print(f"取得したモデル一覧: {all_models[:8]}")
    # エイリアス（latest系）を優先、なければ3.6→その他の順
        latest = [m for m in all_models if "latest" in m and "flash" in m]
        versioned = [m for m in all_models if "3.6" in m or "3." in m and "flash" in m]
        other = [m for m in all_models if "flash" in m and "tts" not in m and "embed" not in m]
        ordered = latest + versioned + other
        if ordered:
            model = ordered[0]
except Exception as e:
    print(f"⚠ モデル一覧取得失敗（デフォルト使用）: {e}")

print(f"📅 {today} の論文を取得中（モデル: {model}）...")

def ask(prompt):
    url = f"{BASE}/{model}:generateContent?key={KEY}"
    result = call_api(url, {"contents":[{"role":"user","parts":[{"text":prompt}]}]})
    text = result.get("candidates",[{}])[0].get("content",{}).get("parts",[{}])[0].get("text","")
    if not text:
        raise RuntimeError(f"空の応答: {json.dumps(result)[:200]}")
    return text

# ─── 論文取得 ───
print("📰 論文を取得中...")
paper_prompt = "整形外科の最新論文4件をJSON配列で返してください。各フィールド: specialty(脊椎/肩/股関節/膝/外傷/肘/手指のいずれか), title(日本語), journal(雑誌名と年月), overview(1〜2文), results(1〜2文), conclusion(1〜2文)。JSONのみ。前置き不要。"

try:
    text = ask(paper_prompt)
    print(f"APIレスポンス（先頭200字）: {text[:200]}")
except Exception as e:
    print(f"❌ 論文取得失敗: {e}")
    sys.exit(1)

m = re.search(r'\[[\s\S]*\]', text)
if not m:
    print(f"❌ JSONが見つかりません。レスポンス: {text[:300]}")
    sys.exit(1)

date_str = datetime.now(JST).strftime("%Y%m%d")
papers = json.loads(m.group(0))
for i, p in enumerate(papers):
    p["id"] = f"auto_{date_str}_{i}"
    p["isNew"] = True
print(f"✅ {len(papers)}件の論文を取得しました")

# ─── 詳細解析 ───
print("📖 詳細解析を生成中...")
new_details = {}
for p in papers:
    try:
        dp = f"整形外科医向けに以下の論文の詳細解説をJSON形式のみで返してください。論文: {p['title']} ({p.get('journal','')}) フィールド: background, methodology, keyFindings, clinicalImpact, limitations, relatedEvidence（各2〜3文）。JSONのみ。"
        dtext = ask(dp)
        dm = re.search(r'\{[\s\S]*\}', dtext)
        if dm:
            new_details[p["id"]] = json.loads(dm.group(0))
            print(f"  ✅ {p['title'][:35]}")
    except Exception as e:
        print(f"  ⚠ 詳細スキップ: {e}")

# ─── ファイル保存 ───
existing = {}
try:
    with open("details.json", encoding="utf-8") as f:
        existing = json.load(f)
except Exception:
    pass
existing.update(new_details)
with open("details.json", "w", encoding="utf-8") as f:
    json.dump(existing, f, ensure_ascii=False, indent=2)
print(f"📁 details.json 更新（累計 {len(existing)}件）")

with open("news.json", "w", encoding="utf-8") as f:
    json.dump({"updated": today, "updated_iso": datetime.now(JST).isoformat(), "papers": papers}, f, ensure_ascii=False, indent=2)
print("✅ 完了")
