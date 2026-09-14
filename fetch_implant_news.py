"""
国内整形外科インプラントメーカーニュース取得スクリプト
毎週月曜日に GitHub Actions から実行される。
SDKを使わずHTTP直接呼び出し。
"""
import json, re, os, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))
today = datetime.now(JST).strftime("%Y年%m月%d日")
KEY = os.environ["GOOGLE_API_KEY"]
BASE = "https://generativelanguage.googleapis.com/v1beta/models"

def get_model():
    try:
        with urllib.request.urlopen(f"{BASE}?key={KEY}", timeout=15) as r:
            data = json.loads(r.read())
        all_models = [m["name"].replace("models/","") for m in data.get("models",[])]
        flash = [m for m in all_models if "flash" in m and "tts" not in m]
        if flash:
            print(f"使用モデル: {flash[0]}")
            return flash[0]
    except Exception as e:
        print(f"モデル取得失敗: {e}")
    return "gemini-2.5-flash"

def ask(prompt, model):
    url = f"{BASE}/{model}:generateContent?key={KEY}"
    body = json.dumps({"contents":[{"role":"user","parts":[{"text":prompt}]}]}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode()[:200]}")

COMPANIES = [
    "Stryker","Zimmer Biomet","DePuy Synthes（J&J）","Smith+Nephew",
    "帝人ナカシマメディカル","メディカルネクスト","HOYAテクノサージカル",
    "Globus Medical","京セラメディカル","日本MDM","Medtronic"
]

model = get_model()
print(f"📅 {today} のインプラントニュースを取得中...")

prompt = f"""日本の整形外科インプラント11社の今週({today})の動向をJSON配列で返してください。
対象: {', '.join(COMPANIES)}
各企業: company(企業名), rating(0〜3), items(配列: category(新製品/薬事承認/臨床データ/提携・契約/人事/その他), title(20字以内), summary(2〜3文))。
情報なければrating:0, items:[]。JSONのみ。"""

text = ask(prompt, model)
m = re.search(r'\[[\s\S]*\]', text)
if not m:
    raise ValueError("JSONが見つかりません:\n" + text[:400])

companies = json.loads(m.group(0))
output = {"updated": today, "updated_iso": datetime.now(JST).isoformat(), "companies": companies}

with open("implant_news.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f"✅ {len(companies)}社分を保存しました")
