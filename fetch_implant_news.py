"""
国内整形外科インプラントメーカーニュース取得スクリプト
毎週月曜日に GitHub Actions から実行される。GOOGLE_API_KEY 環境変数が必要。
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
            return json.loads(r.read()), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.read().decode()[:200]}"
    except urllib.error.URLError as e:
        return None, f"URLError: {e.reason}"

def get_models():
    data, err = call_api(f"{BASE}?key={KEY}")
    if err or not data:
        print(f"モデル一覧取得失敗: {err}")
        return ["gemini-flash-latest", "gemini-flash-lite-latest", "gemini-3.6-flash"]
    all_models = [m["name"].replace("models/", "") for m in data.get("models", [])]
    print(f"取得したモデル一覧: {all_models}")
    skip = ["tts", "embed", "vision"]
    candidates = [m for m in all_models if not any(s in m for s in skip)]
    latest = [m for m in candidates if "latest" in m]
    others = [m for m in candidates if "latest" not in m]
    return latest + others

def ask_with_fallback(prompt, models):
    for model in models:
        print(f"  試行: {model}")
        url = f"{BASE}/{model}:generateContent?key={KEY}"
        result, err = call_api(url, {"contents": [{"role": "user", "parts": [{"text": prompt}]}]})
        if err:
            print(f"  失敗: {err[:100]}")
            continue
        text = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        if text:
            print(f"  成功: {model}")
            return text, model
        print(f"  空の応答")
    return None, None

COMPANIES = [
    "Stryker", "Zimmer Biomet", "DePuy Synthes（J&J）", "Smith+Nephew",
    "帝人ナカシマメディカル", "メディカルネクスト", "HOYAテクノサージカル",
    "Globus Medical", "京セラメディカル", "日本MDM", "Medtronic"
]

models = get_models()
print(f"📅 {today} のインプラントニュースを取得中...")

prompt = f"""日本の整形外科インプラント11社の今週({today})の動向をJSON配列で返してください。
対象: {', '.join(COMPANIES)}
各企業: company(企業名), rating(0〜3), items(配列: category(新製品/薬事承認/臨床データ/提携・契約/人事/その他), title(20字以内), summary(2〜3文))。
情報なければrating:0, items:[]。JSONのみ。"""

text, used_model = ask_with_fallback(prompt, models)
if not text:
    print("すべてのモデルで失敗しました")
    sys.exit(1)

m = re.search(r'\[[\s\S]*\]', text)
if not m:
    print(f"JSONが見つかりません: {text[:300]}")
    sys.exit(1)

companies = json.loads(m.group(0))
output = {"updated": today, "updated_iso": datetime.now(JST).isoformat(), "companies": companies}

with open("implant_news.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f"✅ {len(companies)}社分を保存しました（使用モデル: {used_model}）")
