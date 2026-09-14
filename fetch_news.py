"""
整形外科論文ニュース取得スクリプト
毎日 GitHub Actions から実行される。GOOGLE_API_KEY 環境変数が必要。
SDKを使わずHTTP直接呼び出しのため、パッケージバージョンに依存しない。
"""
import json, re, os, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))
today = datetime.now(JST).strftime("%Y年%m月%d日")
KEY = os.environ["GOOGLE_API_KEY"]
BASE = "https://generativelanguage.googleapis.com/v1beta/models"

def get_model():
    """利用可能なモデルを取得して最適なものを返す"""
    try:
        url = f"{BASE}?key={KEY}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        all_models = [m["name"].replace("models/","") for m in data.get("models",[])]
        flash = [m for m in all_models if "flash" in m and "tts" not in m and "embed" not in m]
        if flash:
            print(f"利用可能なモデル: {flash[:5]}")
            return flash[0]
    except Exception as e:
        print(f"モデル一覧取得失敗: {e}")
    # フォールバック
    for m in ["gemini-2.5-flash","gemini-flash-latest","gemini-2.0-flash","gemini-1.5-flash"]:
        print(f"フォールバック: {m}")
        return m

def ask(prompt, model):
    """Gemini APIを呼び出してテキストを返す"""
    url = f"{BASE}/{model}:generateContent?key={KEY}"
    body = json.dumps({"contents":[{"role":"user","parts":[{"text":prompt}]}]}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        raise RuntimeError(f"HTTP {e.code}: {err[:200]}")

model = get_model()
print(f"📅 {today} の論文を取得中（モデル: {model}）...")

# ─── 論文サマリー取得 ───
paper_prompt = f"整形外科の最新論文4件をJSON配列で返してください。各フィールド: specialty(脊椎/肩/股関節/膝/外傷/肘/手指のいずれか), title(日本語), journal(雑誌名と年月), overview(1〜2文), results(1〜2文), conclusion(1〜2文)。JSONのみ。前置き不要。"

text = ask(paper_prompt, model)
m = re.search(r'\[[\s\S]*\]', text)
if not m:
    raise ValueError("JSONが見つかりません:\n" + text[:400])

date_str = datetime.now(JST).strftime("%Y%m%d")
papers = json.loads(m.group(0))
for i, p in enumerate(papers):
    p["id"]    = f"auto_{date_str}_{i}"
    p["isNew"] = True

print(f"✅ {len(papers)}件の論文を取得しました")

# ─── 各論文の詳細解析を生成 ───
print("📖 詳細解析を生成中...")
new_details = {}
for p in papers:
    try:
        detail_prompt = f"""整形外科医向けに以下の論文の詳細解説をJSON形式のみで返してください。
論文: {p['title']} ({p.get('journal','')})
フィールド: background, methodology, keyFindings, clinicalImpact, limitations, relatedEvidence（各2〜3文）。JSONのみ。"""
        dtext = ask(detail_prompt, model)
        dm = re.search(r'\{[\s\S]*\}', dtext)
        if dm:
            new_details[p["id"]] = json.loads(dm.group(0))
            print(f"  ✅ {p['title'][:35]}...")
    except Exception as e:
        print(f"  ⚠ 詳細生成スキップ: {e}")

# ─── details.json に追記 ───
existing_details = {}
try:
    with open("details.json", encoding="utf-8") as f:
        existing_details = json.load(f)
except Exception:
    pass
existing_details.update(new_details)
with open("details.json", "w", encoding="utf-8") as f:
    json.dump(existing_details, f, ensure_ascii=False, indent=2)
print(f"📁 details.json 更新（累計 {len(existing_details)}件）")

# ─── news.json を保存 ───
with open("news.json", "w", encoding="utf-8") as f:
    json.dump({"updated": today, "updated_iso": datetime.now(JST).isoformat(), "papers": papers},
              f, ensure_ascii=False, indent=2)
print("📰 news.json を保存しました")
