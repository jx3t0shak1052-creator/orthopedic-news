"""
整形外科論文ニュース取得スクリプト（詳細解析も同時生成）
毎日 GitHub Actions から実行される。ANTHROPIC_API_KEY 環境変数が必要。
"""
import anthropic, json, re
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))
today = datetime.now(JST).strftime("%Y年%m月%d日")
client = anthropic.Anthropic()

# ─── 論文サマリー取得 ───
print(f"📅 {today} の論文を取得中...")
msg = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=2000,
    system=(
        "あなたは整形外科の研究アシスタントです。"
        "最新の整形外科文献から8件の論文サマリーをJSON配列のみで返してください"
        "（肩は2件、脊椎・肘・手指・股関節・膝・外傷は各1件）。"
        "各オブジェクトのフィールド: "
        "specialty（脊椎/肩/肘/手指/股関節/膝/外傷のいずれか必須）, "
        "title（日本語タイトル）, journal（雑誌名と掲載年月）, "
        "overview（研究概要2〜3文）, results（主な結果2〜3文）, "
        "conclusion（結論と臨床的考察2〜3文）。"
        "JSONのみを返し、前置きや説明文は絶対に含めないこと。"
    ),
    messages=[{"role": "user", "content":
        f"今日{today}の最新整形外科論文を各分野から（肩は2件、それ以外各1件）紹介してください。"
        "できるだけ2025〜2026年の論文を選んでください。"
        "これまで取り上げた論文と重複しないよう注意してください。"
    }]
)
text = msg.content[0].text
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
        dm = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            system=(
                "あなたは整形外科の専門家です。以下の論文について整形外科医向けの詳細な解説を"
                "JSON形式のみで返してください。フィールド: "
                "background（研究背景と臨床的課題、3〜4文）, "
                "methodology（研究デザイン・対象・方法の詳細、3〜4文）, "
                "keyFindings（主要な発見・数値の詳細、3〜4文）, "
                "clinicalImpact（日本の整形外科診療への臨床的インパクト、3〜4文）, "
                "limitations（研究の限界・課題、2〜3文）, "
                "relatedEvidence（関連エビデンスとの比較・文脈、2〜3文）。"
                "JSONのみを返し、前置きや説明文は含めないこと。"
            ),
            messages=[{"role": "user", "content":
                f"論文タイトル: {p['title']}\n"
                f"雑誌: {p['journal']}\n"
                f"概要: {p['overview']}\n"
                f"結果: {p['results']}\n"
                f"結論: {p['conclusion']}"
            }]
        )
        dtext = dm.content[0].text
        dm2 = re.search(r'\{[\s\S]*\}', dtext)
        if dm2:
            new_details[p["id"]] = json.loads(dm2.group(0))
            print(f"  ✅ {p['title'][:35]}...")
    except Exception as e:
        print(f"  ⚠ 詳細生成スキップ ({p['id']}): {e}")

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
print(f"📁 details.json に {len(new_details)}件の詳細を保存しました（累計 {len(existing_details)}件）")

# ─── news.json を保存 ───
output = {
    "updated":     today,
    "updated_iso": datetime.now(JST).isoformat(),
    "papers":      papers
}
with open("news.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f"📰 news.json を保存しました")
