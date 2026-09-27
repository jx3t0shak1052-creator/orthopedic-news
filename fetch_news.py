"""
整形外科論文ニュース取得スクリプト（PubMed 連携版）
================================================================
【旧版の問題】
  旧版は Gemini に「整形外科の最新論文を7件挙げて」と丸投げしていたため、
  PubMed 等の実データを参照せず、モデルが実在しない論文・誤った書誌情報・
  数値を生成する（ハルシネーション）余地があった。

【本版の方針】
  1) まず PubMed 収載文献を実検索して「実在する論文」を確定させる
     - 主経路   : Europe PMC REST API（PubMed 収載分 = SRC:MED を対象）
                  ※ NCBI の検索APIが障害中でも動くため主経路に採用
     - 副経路   : NCBI E-utilities (esearch + efetch)
     - SEARCH_BACKEND 環境変数で auto / europepmc / pubmed を切替可能
  2) 取得した抄録(abstract)だけを根拠に Gemini へ日本語要約を作らせる
     → プロンプトで「抄録に書かれていない情報を足さないこと」を明示
  3) 出力スキーマは旧版と完全互換（news.json / details.json）
     ＋ pmid / doi / url / title_en / authors / published を追加

【環境変数】
  GOOGLE_API_KEY : Gemini API キー（必須。--dry-run 時は不要）
  NCBI_API_KEY   : NCBI E-utilities 用キー（任意。指定するとレート制限が緩和）
  NCBI_EMAIL     : NCBI 推奨の連絡先（任意）
  SEARCH_BACKEND : auto（既定） / europepmc / pubmed

【使い方】
  python fetch_news.py             # 通常実行（news.json / details.json を更新）
  python fetch_news.py --dry-run   # 検索のみ。書き込みせず結果を表示
"""
import json, os, re, sys, time, random, html
import urllib.parse, urllib.request, urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))
NOW = datetime.now(JST)
TODAY = NOW.strftime("%Y年%m月%d日")
DATE_STR = NOW.strftime("%Y%m%d")
DRY_RUN = "--dry-run" in sys.argv

GEMINI_KEY = os.environ.get("GOOGLE_API_KEY", "")
NCBI_API_KEY = os.environ.get("NCBI_API_KEY", "")
NCBI_EMAIL = os.environ.get("NCBI_EMAIL", "orthopedic-news@example.com")
NCBI_TOOL = "orthopedic-news"
BACKEND = (os.environ.get("SEARCH_BACKEND") or "auto").lower()

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
EPMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

UA = f"{NCBI_TOOL}/2.0 (+https://github.com/jx3t0shak1052-creator/orthopedic-news)"

# ──────────────────────────────────────────────────────────────
# 専門分野ごとの検索キーワード（英語）
#   各分野を「1日1件ずつ」カバーするために分野ごとに検索する
# ──────────────────────────────────────────────────────────────
SPECIALTIES = {
    "脊椎": ["spine", "spinal", "lumbar", "cervical spine", "vertebral",
             "intervertebral disc", "spondylolisthesis", "spinal fusion", "myelopathy"],
    "肩": ["shoulder", "rotator cuff", "glenohumeral", "acromioclavicular",
           "shoulder arthroplasty", "bankart", "latarjet", "shoulder instability"],
    "股関節": ["hip", "hip fracture", "total hip arthroplasty", "acetabular",
              "femoral head", "femoroacetabular impingement", "hip arthroscopy"],
    "膝": ["knee", "anterior cruciate ligament", "meniscus", "meniscal",
           "total knee arthroplasty", "knee osteoarthritis", "patellofemoral", "unicompartmental"],
    "外傷": ["fracture", "polytrauma", "intramedullary nail", "open fracture",
             "tibial fracture", "femoral shaft", "calcaneus", "nonunion", "ankle fracture"],
    "肘": ["elbow", "olecranon", "distal humerus", "medial epicondyle",
           "radial head", "elbow arthroplasty", "elbow instability"],
    "手指": ["hand surgery", "wrist", "scaphoid", "distal radius", "flexor tendon",
             "thumb", "carpal tunnel", "finger replantation", "dupytren"],
}

# エビデンス上位の研究デザイン（Europe PMC の PUB_TYPE）
HIGH_LEVEL_TYPES = [
    "Randomized Controlled Trial", "Meta-Analysis", "Systematic Review",
    "Clinical Trial", "Practice Guideline", "Multicenter Study",
]
# 優先度スコア（大きいほど先に採用）
TYPE_SCORE = {
    "Randomized Controlled Trial": 100, "Meta-Analysis": 95,
    "Systematic Review": 90, "Practice Guideline": 90,
    "Clinical Trial": 70, "Multicenter Study": 60,
}

# 整形外科の中核ジャーナル（該当すると選定で優先される）
CORE_JOURNALS = [
    "j bone joint surg", "bone joint j", "jbjs", "clin orthop relat res",
    "j arthroplasty", "am j sports med", "arthroscopy", "spine",
    "eur spine j", "spine j", "global spine j", "j neurosurg spine",
    "knee surg sports traumatol arthrosc", "j shoulder elbow surg", "jses",
    "j hand surg", "j wrist surg", "injury", "foot ankle int", "acta orthop",
    "orthop j sports med", "ojsm", "j orthop trauma", "hip int",
    "j am acad orthop surg", "jaaos", "efort open rev", "int orthop",
    "arch orthop trauma surg", "skeletal radiol", "osteoporos int",
    "j bone miner res", "bone", "bmj", "lancet", "n engl j med", "jama",
]



# ──────────────────────────────────────────────────────────────
# HTTP ヘルパー
# ──────────────────────────────────────────────────────────────
def http_get_json(url, tries=3, timeout=60):
    """JSON を取得。失敗時は (None, エラー文字列)"""
    last = ""
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8")), None
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:200]}"
        except urllib.error.URLError as e:
            last = f"URLError: {e.reason}"
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
        if i < tries - 1:
            time.sleep(2 * (i + 1))
    return None, last


def http_get_text(url, tries=3, timeout=60):
    last = ""
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "ignore"), None
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:200]}"
        except urllib.error.URLError as e:
            last = f"URLError: {e.reason}"
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
        if i < tries - 1:
            time.sleep(2 * (i + 1))
    return None, last


def clean_text(s):
    """HTMLタグ・実体参照を除去して1行に整える"""
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


# ──────────────────────────────────────────────────────────────
# 経路1: Europe PMC（PubMed 収載文献 = SRC:MED）
# ──────────────────────────────────────────────────────────────
def epmc_query(keywords, days=None, frm=None, to=None, high_level=True):
    kw = " OR ".join(f'TITLE_ABS:"{k}"' for k in keywords)
    q = f"(SRC:MED) AND ({kw})"
    if frm and to:
        q += f" AND (FIRST_PDATE:[{frm} TO {to}])"
    elif days:
        q += f" AND (FIRST_PDATE:[NOW-{days}DAY TO NOW])"
    if high_level:
        pt = " OR ".join(f'PUB_TYPE:"{t}"' for t in HIGH_LEVEL_TYPES)
        q += f" AND ({pt})"
    return q


def epmc_search(keywords, days=14, high_level=True, page_size=25):
    """Europe PMC を検索して論文レコードのリストを返す"""
    q = epmc_query(keywords, days=days, high_level=high_level)
    params = {
        "query": q, "format": "json", "resultType": "core",
        "pageSize": str(page_size), "sort": "P_PDATE_D desc",
    }
    url = EPMC_SEARCH + "?" + urllib.parse.urlencode(params)
    data, err = http_get_json(url)
    if err:
        return [], err
    raw = (data.get("resultList", {}) or {}).get("result", []) or []
    return [normalize_epmc(x) for x in raw], None


# ──────────────────────────────────────────────────────────────
# 経路2: NCBI E-utilities（esearch → efetch）
# ──────────────────────────────────────────────────────────────
def eutils_common(params):
    params = dict(params)
    params["tool"] = NCBI_TOOL
    params["email"] = NCBI_EMAIL
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
    return params


def pubmed_search(keywords, days=14, high_level=True, retmax=25):
    kw = " OR ".join(f'"{k}"[Title/Abstract]' for k in keywords)
    term = f"({kw})"
    if high_level:
        pt = " OR ".join(f'"{t}"[Publication Type]' for t in HIGH_LEVEL_TYPES)
        term += f" AND ({pt})"
    term += f" AND (\"last {days} days\"[dp])"

    url = f"{EUTILS}/esearch.fcgi?" + urllib.parse.urlencode(eutils_common({
        "db": "pubmed", "term": term, "retmax": retmax,
        "retmode": "json", "sort": "date",
    }))
    data, err = http_get_json(url)
    if err:
        return [], err
    res = (data or {}).get("esearchresult", {}) or {}
    if res.get("ERROR"):
        return [], f"esearch ERROR: {res['ERROR']}"
    ids = res.get("idlist", []) or []
    if not ids:
        return [], None
    return pubmed_fetch(ids), None


def pubmed_fetch(pmids):
    """PMID リストを efetch で取得してレコード dict に変換"""
    url = f"{EUTILS}/efetch.fcgi?" + urllib.parse.urlencode(eutils_common({
        "db": "pubmed", "id": ",".join(pmids), "retmode": "xml",
    }))
    xml, err = http_get_text(url)
    if err:
        return []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        print(f"  ⚠ efetch XML 解析失敗: {e}")
        return []

    out = []
    for art in root.findall(".//PubmedArticle"):
        rec = {}
        pmid = art.findtext(".//MedlineCitation/PMID") or ""
        rec["pmid"] = pmid
        rec["title"] = clean_text(art.findtext(".//Article/ArticleTitle"))
        journal = art.find(".//Article/Journal")
        if journal is not None:
            rec["journal_title"] = (journal.findtext("ISOAbbreviation")
                                    or journal.findtext("Title") or "").strip().rstrip(".")
            rec["journal_year"] = journal.findtext(".//PubDate/Year") or ""
            rec["journal_month"] = journal.findtext(".//PubDate/Month") or ""
        abs_parts = []
        for a in art.findall(".//Article/Abstract/AbstractText"):
            label = a.get("Label") or ""
            body = clean_text("".join(a.itertext()))
            abs_parts.append(f"{label}: {body}" if label else body)
        rec["abstract"] = clean_text(" ".join(abs_parts))
        authors = []
        for a in art.findall(".//AuthorList/Author")[:6]:
            ln, fn = a.findtext("LastName"), a.findtext("Initials")
            if ln:
                authors.append(f"{ln} {fn}".strip())
            elif a.findtext("CollectiveName"):
                authors.append(a.findtext("CollectiveName"))
        rec["authors"] = ", ".join(authors)
        rec["doi"] = ""
        for eid in art.findall(".//ArticleIdList/ArticleId"):
            if eid.get("IdType") == "doi":
                rec["doi"] = (eid.text or "").strip()
        pts = [clean_text(p.text or "") for p in art.findall(".//PublicationTypeList/PublicationType")]
        rec["pub_types"] = pts
        rec["published"] = art.findtext(".//Article/Journal/JournalIssue/PubDate/MedlineDate") or ""
        rec["source"] = "PubMed"
        rec["url"] = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""
        out.append(rec)
    return out


# ──────────────────────────────────────────────────────────────
# レコード正規化・選定
# ──────────────────────────────────────────────────────────────
MONTH_MAP = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
             "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}


def normalize_epmc(r):
    """Europe PMC のレコードを共通形式に変換"""
    ji = r.get("journalInfo", {}) or {}
    j = ji.get("journal", {}) or {}
    year = str(ji.get("yearOfPublication") or r.get("pubYear") or "")
    month = str(ji.get("monthOfPublication") or "")
    pts = ((r.get("pubTypeList", {}) or {}).get("pubType", []) or [])
    return {
        "pmid": r.get("pmid") or (r.get("id") if r.get("source") == "MED" else "") or "",
        "doi": (r.get("doi") or "").strip(),
        "title": clean_text(r.get("title")),
        "abstract": clean_text(r.get("abstractText")),
        "authors": clean_text(r.get("authorString")),
        "journal_title": (j.get("medlineAbbreviation") or j.get("title") or "").strip().rstrip("."),
        "journal_year": year,
        "journal_month": month,
        "pub_types": [clean_text(p) for p in pts],
        "published": (r.get("firstPublicationDate") or "").strip(),
        "source": "Europe PMC (PubMed)",
    }


def finalize(rec):
    """共通形式のレコードに表示用フィールドを付与"""
    pmid = rec.get("pmid", "")
    rec["url"] = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""
    y, m = rec.get("journal_year", ""), rec.get("journal_month", "")
    mm = ""
    if m:
        mm = f"{int(m)}月" if str(m).isdigit() else f"{MONTH_MAP.get(str(m)[:3].lower(), '')}月"
    jt = rec.get("journal_title") or "Journal"
    rec["journal_display"] = f"{jt}, {y}年{mm}" if y else jt
    return rec


def score_record(rec):
    """採用優先度スコア（研究デザイン + 新しさ）"""
    s = 0
    for pt in rec.get("pub_types", []):
        for t, v in TYPE_SCORE.items():
            if pt.lower() == t.lower():
                s = max(s, v)
    pub = rec.get("published") or ""
    if re.match(r"\d{4}-\d{2}-\d{2}", pub):
        try:
            d = datetime.strptime(pub[:10], "%Y-%m-%d")
            s += max(0, 30 - (NOW.date() - d.date()).days)  # 新しいほど加点
        except ValueError:
            pass
    return s


def title_hits(title, keywords):
    """タイトルに含まれる分野キーワードの数（関連度が高い論文ほど大きい）"""
    t = (title or "").lower()
    return sum(1 for k in keywords if k.lower() in t)


def relevance(rec, keywords):
    """タイトル一致を3点、抄録一致を1点として関連度を算出"""
    t = (rec.get("title") or "").lower()
    a = (rec.get("abstract") or "").lower()
    s = 0
    for k in keywords:
        kl = k.lower()
        if kl in t:
            s += 3
        elif kl in a:
            s += 1
    return s


def is_core_journal(rec):
    """整形外科の中核誌かどうか"""
    j = (rec.get("journal_title") or "").lower()
    return any(c in j for c in CORE_JOURNALS)


def search_specialty(name, keywords, used_pmids):
    """1分野について、条件を段階的に緩めて論文を1件選ぶ"""
    # (過去日数, 上位デザイン限定, タイトル一致必須) の順に試す
    #  → まず「タイトルに分野語を含む質の高い論文」を狙い、
    #    見つからない場合のみ条件を緩める
    attempts = [
        (14, True, True), (14, False, True), (45, False, True),
        (60, False, False), (180, False, False), (365, False, False),
    ]
    for days, high, require_title in attempts:
        recs = []
        using = None
        if BACKEND in ("auto", "europepmc"):
            recs, err = epmc_search(keywords, days=days, high_level=high)
            using = "Europe PMC"
            if err:
                print(f"    Europe PMC 失敗: {err[:120]}")
                recs = []
        if not recs and BACKEND in ("auto", "pubmed"):
            recs, err = pubmed_search(keywords, days=days, high_level=high)
            using = "PubMed E-utilities"
            if err:
                print(f"    PubMed 失敗: {err[:120]}")
                recs = []
        if not recs:
            continue

        cands = []
        for r in recs:
            rec = finalize(r)
            if not rec.get("abstract"):
                continue                      # 抄録が無いものは要約の根拠が無いため除外
            if not rec.get("title"):
                continue
            pmid = rec.get("pmid") or rec.get("title")[:60]
            if pmid in used_pmids:
                continue                      # 他分野で使用済みは除外
            th = title_hits(rec["title"], keywords)
            if require_title and th == 0:
                continue                      # タイトルに分野語が無いものは除外
            rec["_title_hits"] = th
            cands.append(rec)
        if not cands:
            continue

        # 優先順位: タイトル一致数 → 中核誌 → 関連度 → 研究デザイン → 新しさ
        cands.sort(key=lambda r: (
            r["_title_hits"],
            1 if is_core_journal(r) else 0,
            relevance(r, keywords),
            score_record(r),
        ), reverse=True)
        pick = cands[0]
        key = pick.get("pmid") or pick["title"][:60]
        used_pmids.add(key)
        print(f"    ✅ [{using}] 直近{days}日 / 上位デザイン={high} / タイトル一致必須={require_title}"
              f" → {len(cands)}件中から採用 (PMID:{pick.get('pmid') or 'n/a'}, "
              f"{pick.get('published') or '日付不明'}, 中核誌:{'○' if is_core_journal(pick) else '×'})")
        return pick
    return None


# ──────────────────────────────────────────────────────────────
# Gemini
# ──────────────────────────────────────────────────────────────
def gemini_models():
    data, err = http_get_json(f"{GEMINI_BASE}?key={GEMINI_KEY}")
    if err or not data:
        print(f"モデル一覧取得失敗: {err}")
        return ["gemini-flash-latest", "gemini-flash-lite-latest"]
    names = [m["name"].replace("models/", "") for m in data.get("models", [])]
    skip = ("tts", "embed", "vision", "image")
    cand = [n for n in names if not any(s in n for s in skip)]
    return [n for n in cand if "latest" in n] + [n for n in cand if "latest" not in n]


def gemini_ask(prompt, models):
    body = json.dumps({"contents": [{"role": "user", "parts": [{"text": prompt}]}]}).encode()
    for model in models:
        url = f"{GEMINI_BASE}/{model}:generateContent?key={GEMINI_KEY}"
        try:
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=90) as r:
                data = json.loads(r.read())
            text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            if text:
                return text, model
        except urllib.error.HTTPError as e:
            print(f"    {model}: HTTP {e.code}")
        except Exception as e:
            print(f"    {model}: {type(e).__name__}")
        time.sleep(1)
    return None, None


def parse_json_block(text, bracket="{"):
    if not text:
        return None
    m = re.search(r"\[[\s\S]*\]" if bracket == "[" else r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


GROUNDING_RULE = (
    "【厳守】以下の抄録(abstract)に書かれている内容だけを根拠にすること。"
    "抄録に無い数値・試験名・結論を推測で補ってはならない。"
    "抄録から読み取れない項目は「抄録に記載なし」と明記すること。"
)

SUMMARY_PROMPT = """あなたは整形外科の専門家です。以下は PubMed から取得した実在の論文です。
医師向けニュース記事用に、正確な日本語で JSON のみを返してください（前置き・説明文・コードフェンスは不要）。

{rule}

分野: {specialty}
英語タイトル: {title}
雑誌: {journal}
著者: {authors}
抄録:
{abstract}

返すJSONのキー:
- title_ja : 英語タイトルの正確な日本語訳（原題の意味を変えないこと。30〜80字程度）
- overview : 研究の目的と背景を1〜2文で
- results  : 主要な結果を1〜2文で。数値は抄録に記載があるもののみ記載
- conclusion : 結論・臨床的意義を1〜2文で
"""

DETAIL_PROMPT = """あなたは整形外科の専門家です。以下は PubMed から取得した実在の論文の抄録です。
医師向けの詳細解説を JSON のみで返してください（前置き・説明文・コードフェンスは不要）。

{rule}
各項目は日本語で2〜3文。抄録に情報が無い項目は「抄録に記載なし」とだけ書くこと。

英語タイトル: {title}
雑誌: {journal}
抄録:
{abstract}

返すJSONのキー:
- background : 研究背景と臨床的課題
- methodology : 研究デザイン・対象・方法の詳細
- keyFindings : 主要な発見・数値の詳細
- clinicalImpact : 日本の整形外科診療への臨床的インパクト
- limitations : 研究の限界・課題
- relatedEvidence : 関連エビデンスとの比較・文脈
"""


# ──────────────────────────────────────────────────────────────
# メイン
# ──────────────────────────────────────────────────────────────
def main():
    if not GEMINI_KEY and not DRY_RUN:
        print("GOOGLE_API_KEY が設定されていません")
        sys.exit(1)

    models = [] if DRY_RUN else gemini_models()

    print("=" * 60)
    print(f"📅 {TODAY} の整形外科論文を PubMed から取得します")
    print(f"   検索経路: {BACKEND} / dry-run: {DRY_RUN}")
    print("=" * 60)

    # 分野の表示順（日付シードでシャッフル。カバー範囲は常に全7分野）
    order = list(SPECIALTIES.keys())
    random.seed(int(DATE_STR))
    random.shuffle(order)
    print(f"本日の配信順: {', '.join(order)}\n")

    used = set()
    collected = []
    for i, sp in enumerate(order):
        print(f"[{i+1}/{len(order)}] {sp} を検索中...")
        try:
            rec = search_specialty(sp, SPECIALTIES[sp], used)
        except Exception as e:
            print(f"    ⚠ 検索エラー: {type(e).__name__}: {e}")
            rec = None
        if not rec:
            print(f"    ⚠ {sp}: 条件に合う論文が見つかりませんでした")
            continue
        collected.append((sp, rec))
        time.sleep(0.5)   # API への負荷軽減

    if not collected:
        print("\n❌ 論文を1件も取得できませんでした。検索APIの状態を確認してください。")
        sys.exit(1)

    print(f"\n📚 実在論文 {len(collected)}件を取得しました。日本語要約を生成します...\n")

    papers, new_details, failed = [], {}, []
    for i, (sp, rec) in enumerate(collected):
        pid = f"auto_{DATE_STR}_{i}"
        abstract = rec["abstract"][:2500]

        summary = None
        if not DRY_RUN:
            prompt = SUMMARY_PROMPT.format(
                rule=GROUNDING_RULE, specialty=sp, title=rec["title"],
                journal=rec["journal_display"], authors=rec.get("authors", ""),
                abstract=abstract)
            text, used_model = gemini_ask(prompt, models)
            summary = parse_json_block(text)
            if not summary:
                print(f"  ⚠ 要約生成失敗: {rec['title'][:40]}... → この論文はスキップ")
                failed.append(rec["title"])
                continue

        paper = {
            "specialty": sp,
            "title": (summary or {}).get("title_ja") or rec["title"],
            "title_en": rec["title"],
            "journal": rec["journal_display"],
            "authors": rec.get("authors", ""),
            "overview": (summary or {}).get("overview", ""),
            "results": (summary or {}).get("results", ""),
            "conclusion": (summary or {}).get("conclusion", ""),
            "pmid": rec.get("pmid", ""),
            "doi": rec.get("doi", ""),
            "url": rec.get("url", ""),
            "published": rec.get("published", ""),
            "source": rec.get("source", "PubMed"),
            "id": pid,
            "isNew": True,
        }
        papers.append(paper)
        print(f"  ✅ [{sp}] {paper['title'][:44]}  (PMID:{rec.get('pmid') or 'n/a'})")

        # 詳細解析
        if not DRY_RUN:
            dtext, _ = gemini_ask(DETAIL_PROMPT.format(
                rule=GROUNDING_RULE, title=rec["title"],
                journal=rec["journal_display"], abstract=abstract), models)
            d = parse_json_block(dtext)
            if d:
                new_details[pid] = d
            time.sleep(0.5)

    if DRY_RUN:
        print("\n--- dry-run 結果 ---")
        for sp, rec in collected:
            print(f"[{sp}] {rec['title']}")
            print(f"     {rec['journal_display']} / {rec.get('published')} / {rec.get('url')}")
            print(f"     抄録 {len(rec['abstract'])}字 / デザイン: {', '.join(rec.get('pub_types', [])[:3])}")
        print("\n(dry-run のためファイルは書き換えていません)")
        return

    if not papers:
        print("\n❌ 要約を1件も生成できませんでした（Gemini API の状態・キーを確認してください）")
        sys.exit(1)

    # details.json は既存分を保持したまま追記
    existing = {}
    try:
        with open("details.json", encoding="utf-8") as f:
            existing = json.load(f)
    except Exception:
        pass
    existing.update(new_details)
    with open("details.json", "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    print(f"\ndetails.json 更新（累計 {len(existing)}件 / 今回追加 {len(new_details)}件）")

    with open("news.json", "w", encoding="utf-8") as f:
        json.dump({
            "updated": TODAY,
            "updated_iso": NOW.isoformat(),
            "source": "PubMed",
            "papers": papers,
        }, f, ensure_ascii=False, indent=2)
    print(f"news.json 更新（{len(papers)}件）")

    if failed:
        print(f"\n⚠ 要約生成に失敗した論文 {len(failed)}件:")
        for t in failed:
            print(f"   - {t[:70]}")
    print("\n✅ 完了")


if __name__ == "__main__":
    main()
