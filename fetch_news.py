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
    print("GOOGLE_API_KEY が設定されていません")
    sys.exit(1)

BASE = "https://generativelanguage.googleapis.com/v1beta/models"

def call_api(url, body=None):
    if body:
        data = json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    else:
        req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode()[:300]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"URLError: {e.reason}")

def get_model():
    # モデル一覧を取得して最適なものを選ぶ
    try:
        data = call_api(f"{BASE}?key={KEY}")
        all_models = [m["name"].replace("models/", "") for m in data.get("models", [])]
        print(f"取得したモデル一覧: {all_models[:8]}")
        # latest系エイリアスを優先
        for m in all_models:
            if "flash" in m and "latest" in m and "tts" not in m:
                return m
        # バージョン指定モデルを試す
        for m in all_models:
            if "flash" in m and "tts" not in m and "embed" not in m:
                return m
    except Exception as e:
        print(f"モデル一覧取得失敗: {e}")
    # フォールバック
    return "gemini-3.6-flash"

def ask(prompt, model):
    url = f"{BASE}/{model}:generateContent?key={KEY}"
    result = call_api(url, {"contents": [{"role": "user", "parts": [{"text": prompt}]}]})
    text = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
    if not text:
        raise RuntimeError(f"空の応答: {json.dumps(result)[:200]}")
    return text

# モデル選択
model = get_model()
print(f"使用モデル: {model}")
print(f"論文を取得中（{today}）...")

# 論文取得
paper_prompt = "整形外科の最新論文4件をJSON配列で返してください。各フィールド: specialty(脊椎/肩/股関節/膝/外傷/肘/手指のいずれか), title(日本語), journal(雑誌名と年月), overview(1〜2文), results(1〜2文), conclusion(1〜2文)。JSONのみ。前置き不要。"

try:
    text = ask(paper_prompt, model)
    print(f"レスポンス先頭: {text[:200]}")
except Exception as e:
    print(f"論文取得失敗: {e}")
    sys.exit(1)

m = re.search(r'\[[\s\S]*\]', text)
if not m:
    print(f"JSONが見つかりません: {text[:300]}")
    sys.exit(1)

date_str = datetime.now(JST).strftime("%Y%m%d")
papers = json.loads(m.group(0))
for i, p in enumerate(papers):
    p["id"] = f"auto_{date_str}_{i}"
    p["isNew"] = True
print(f"{len(papers)}件の論文を取得しました")

# 詳細解析
new_details = {}
for p in papers:
    try:
        dp = f"整形外科医向けに以下の論文の詳細解説をJSON形式のみで返してください。論文: {p['title']} ({p.get('journal', '')}) フィールド: background, methodology, keyFindings, clinicalImpact, limitations, relatedEvidence（各2〜3文）。JSONのみ。"
        dtext = ask(dp, model)
        dm = re.search(r'\{[\s\S]*\}', dtext)
        if dm:
            new_details[p["id"]] = json.loads(dm.group(0))
            print(f"詳細生成: {p['title'][:35]}")
    except Exception as e:
        print(f"詳細スキップ: {e}")

# details.json 更新
existing = {}
try:
    with open("details.json", encoding="utf-8") as f:
        existing = json.load(f)
except Exception:
    pass
existing.update(new_details)
with open("details.json", "w", encoding="utf-8") as f:
    json.dump(existing, f, ensure_ascii=False, indent=2)
print(f"details.json 更新（累計 {len(existing)}件）")

# news.json 保存
with open("news.json", "w", encoding="utf-8") as f:
    json.dump({
        "updated": today,
        "updated_iso": datetime.now(JST).isoformat(),
        "papers": papers
    }, f, ensure_ascii=False, indent=2)
print("完了")
