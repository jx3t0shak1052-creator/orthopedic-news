"""
整形外科論文ニュース取得スクリプト
毎日 GitHub Actions から実行される。GOOGLE_API_KEY 環境変数が必要。
"""
import json, re, os, sys, urllib.request, urllib.error, random
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
        err_body = e.read().decode()[:300]
        return None, f"HTTP {e.code}: {err_body}"
    except urllib.error.URLError as e:
        return None, f"URLError: {e.reason}"

def get_models():
    """利用可能なモデル一覧を取得。テキスト生成に使えるものを返す"""
    data, err = call_api(f"{BASE}?key={KEY}")
    if err or not data:
        print(f"モデル一覧取得失敗: {err}")
        return ["gemini-flash-latest", "gemini-flash-lite-latest", "gemini-3.6-flash"]
    all_models = [m["name"].replace("models/", "") for m in data.get("models", [])]
    print(f"取得したモデル一覧: {all_models}")
    # TTS・embed系を除外、latest系を優先
    skip = ["tts", "embed", "vision"]
    candidates = [m for m in all_models if not any(s in m for s in skip)]
    # latest系を先頭に
    latest = [m for m in candidates if "latest" in m]
    others = [m for m in candidates if "latest" not in m]
    return latest + others

def ask(prompt, model):
    """指定モデルでAPIを呼ぶ。成功時はテキスト、失敗時は(None, エラー文字列)"""
    url = f"{BASE}/{model}:generateContent?key={KEY}"
    result, err = call_api(url, {"contents": [{"role": "user", "parts": [{"text": prompt}]}]})
    if err:
        return None, err
    text = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
    if not text:
        return None, f"空の応答: {json.dumps(result)[:100]}"
    return text, None

def ask_with_fallback(prompt, models):
    """全モデルを試して最初に成功したものを返す"""
    for model in models:
        print(f"  試行: {model}")
        text, err = ask(prompt, model)
        if text:
            print(f"  成功: {model}")
            return text, model
        print(f"  失敗: {err[:100]}")
    return None, None

# モデル一覧取得
models = get_models()
print(f"候補モデル数: {len(models)}")
print(f"論文を取得中（{today}）...")

# ─── 専門分野のランダム均等選択 ───────────────────────────────
# 7つの専門分野からその日の日付をシードに4つをランダム選択
# → 毎日異なる組み合わせになり、偏りなく全科がカバーされる
ALL_SPECIALTIES = ["脊椎", "肩", "股関節", "膝", "外傷", "肘", "手指"]
date_str = datetime.now(JST).strftime("%Y%m%d")
random.seed(int(date_str))
selected_specialties = ALL_SPECIALTIES[:]
random.shuffle(selected_specialties)
print(f"本日の配信順: {', '.join(selected_specialties)}")
# ────────────────────────────────────────────────────────────────

# 論文取得（全7分野を均等に1件ずつ）
paper_prompt = (
    f"整形外科の最新論文を以下の専門分野から各1件ずつ、合計7件をJSON配列で返してください。"
    f"必ずこの7分野を漏れなく1件ずつカバーしてください: {', '.join(selected_specialties)}。"
    f"各フィールド: specialty(上記の指定分野名をそのまま使用), title(日本語), journal(雑誌名と年月), "
    f"overview(1〜2文), results(1〜2文), conclusion(1〜2文)。JSONのみ。前置き不要。"
)

text, used_model = ask_with_fallback(paper_prompt, models)
if not text:
    print("すべてのモデルで失敗しました")
    sys.exit(1)

m = re.search(r'\[[\s\S]*\]', text)
if not m:
    print(f"JSONが見つかりません: {text[:300]}")
    sys.exit(1)

papers = json.loads(m.group(0))
for i, p in enumerate(papers):
    p["id"] = f"auto_{date_str}_{i}"
    p["isNew"] = True
print(f"{len(papers)}件の論文を取得しました（使用モデル: {used_model}）")

# 詳細解析
new_details = {}
for p in papers:
    try:
        dp = f"整形外科医向けに以下の論文の詳細解説をJSON形式のみで返してください。論文: {p['title']} ({p.get('journal', '')}) フィールド: background, methodology, keyFindings, clinicalImpact, limitations, relatedEvidence（各2〜3文）。JSONのみ。"
        dtext, _ = ask_with_fallback(dp, [used_model] + [m for m in models if m != used_model][:2])
        if dtext:
            dm = re.search(r'\{[\s\S]*\}', dtext)
            if dm:
                new_details[p["id"]] = json.loads(dm.group(0))
                print(f"詳細生成: {p['title'][:35]}")
    except Exception as e:
        print(f"詳細スキップ: {e}")

# ファイル保存
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

with open("news.json", "w", encoding="utf-8") as f:
    json.dump({
        "updated": today,
        "updated_iso": datetime.now(JST).isoformat(),
        "papers": papers
    }, f, ensure_ascii=False, indent=2)
print("完了")
