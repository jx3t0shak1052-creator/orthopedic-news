"""
国内整形外科インプラントメーカーニュース取得スクリプト
毎週月曜日に GitHub Actions から実行される。
"""
import anthropic, json, re
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))
today = datetime.now(JST).strftime("%Y年%m月%d日")
client = anthropic.Anthropic()

COMPANIES = [
    "Stryker（ストライカー）",
    "Zimmer Biomet（ジンマー・バイオメット）",
    "DePuy Synthes（J&J）",
    "Smith+Nephew（スミス＆ネフュー）",
    "帝人ナカシマメディカル",
    "メディカルネクスト",
    "HOYAテクノサージカル",
    "Globus Medical（グローバスメディカル）",
    "京セラメディカル",
    "日本MDM",
    "Medtronic（メドトロニック）"
]

print(f"📅 {today} のインプラントメーカーニュースを取得中...")

message = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=3000,
    system="""あなたは日本の整形外科インプラント業界の専門アナリストです。
以下の11社について、日本国内の最新動向（直近1週間〜1ヶ月）をJSON配列で返してください。

各企業オブジェクトのフィールド:
- company: 企業名（略称可）
- rating: 重要度（3=重要な動き/新製品・承認, 2=注目の動き/提携・拡充, 1=軽微な動き, 0=特筆なし）
- items: ニュース項目の配列。各項目は:
  - category: カテゴリ（新製品/薬事承認/臨床データ/提携・契約/人事/その他）
  - title: 短いタイトル（20字以内）
  - summary: 要約（2〜3文）

情報がない場合は rating:0, items:[] でよい。
JSONのみを返し、前置きや説明文は含めないこと。""",
    messages=[{
        "role": "user",
        "content": f"""今週（{today}時点）の以下11社の日本国内インプラント最新動向を報告してください:
{chr(10).join('- ' + c for c in COMPANIES)}

骨・関節外科（脊椎・肩・膝・股関節・外傷）領域に関連する情報を重点的に。
PMDA承認、新製品発売、国内臨床試験、学会発表、代理店変更、人事なども含めてください。"""
    }]
)

text = message.content[0].text
m = re.search(r'\[[\s\S]*\]', text)
if not m:
    raise ValueError("JSONが見つかりません:\n" + text[:400])

companies = json.loads(m.group(0))

output = {
    "updated": today,
    "updated_iso": datetime.now(JST).isoformat(),
    "companies": companies
}

with open("implant_news.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"✅ {len(companies)}社分のニュースを implant_news.json に保存しました")
for c in companies:
    stars = "★" * c.get("rating", 0) + "☆" * (3 - c.get("rating", 0))
    items = len(c.get("items", []))
    print(f"  {stars} {c.get('company','')} ({items}件)")
