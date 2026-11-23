"""Generate the app's G/J/K/L snapshot from the official full medical fee master."""
import argparse
import csv
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen
from zipfile import ZipFile

MASTER = 'https://www.hpdx.or.jp/smph/seikyushiharai/tensuhyo/kihonmasta/kihonmasta_01.html'
NOTICE = 'https://www.mhlw.go.jp/stf/newpage_67729.html'
INDEX = 'https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/kenkou_iryou/iryouhoken/index.html'
OUT = Path(__file__).resolve().parent / 'data/kj-master.json'
ZIP_NAME = re.compile(r'/s_ALL(\d{8})\.zip$', re.I)


class Links(HTMLParser):
    def __init__(self, html, base):
        super().__init__()
        self.base = base
        self.current = None
        self.links = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.current = [urljoin(self.base, dict(attrs).get('href', '')), '']

    def handle_data(self, text):
        if self.current:
            self.current[1] += text

    def handle_endtag(self, tag):
        if tag == 'a' and self.current:
            url, title = self.current
            self.links.append((url, unicodedata.normalize('NFKC', ' '.join(title.split()))))
            self.current = None


def download(url, cap=16_000_000):
    allowed = {'www.hpdx.or.jp', 'www.mhlw.go.jp'}
    if urlsplit(url).scheme != 'https' or urlsplit(url).netloc not in allowed:
        raise ValueError('Unknown source')
    with urlopen(Request(url, headers={'User-Agent': 'Orthopedic-News KJ master updater/1.0'}), timeout=35) as res:
        if urlsplit(res.url).scheme != 'https' or urlsplit(res.url).netloc not in allowed:
            raise ValueError('Unexpected source redirect')
        data = res.read(cap + 1)
    if len(data) > cap:
        raise ValueError('Source exceeds size limit')
    return data


def latest_master(html, today):
    found = []
    for url, _ in Links(html, MASTER).links:
        p = urlsplit(url)
        m = ZIP_NAME.search(p.path)
        if p.netloc == 'www.hpdx.or.jp' and m:
            stamp = datetime.strptime(m[1], '%Y%m%d').date()
            if stamp <= today:
                found.append((stamp, url))
    if not found:
        raise ValueError('Official full master ZIP link not found')
    return max(found)


def notice_info(fetch=download):
    index = Links(fetch(INDEX).decode('utf-8-sig'), INDEX)
    editions = [(8, NOTICE)]
    for url, title in index.links:
        m = re.fullmatch(r'令和\s*(\d+)\s*年度\s*診療報酬改定(?:について)?', title)
        if m and urlsplit(url).netloc == 'www.mhlw.go.jp':
            editions.append((int(m[1]), url))
    edition, url = max(editions, key=lambda pair: pair[0])
    body = fetch(url).decode('utf-8-sig')
    links = [(u, t) for u, t in Links(body, url).links if urlsplit(u).netloc == 'www.mhlw.go.jp'
             and (urlsplit(u).path.lower().endswith(('.pdf', '.xlsx', '.csv', '.zip')) or '訂正' in t)
             and not t.startswith(('本文へ', 'ページの先頭'))]
    # Also detect changes to an index that loads attachments separately (not a PDF-content monitor).
    content = re.split(r'<(?:main\b|[^>]+\bid=[\'\"]content[\'\"])', body, maxsplit=1, flags=re.I)[-1]
    content = re.split(r'<footer\b', content, maxsplit=1, flags=re.I)[0]
    content = re.sub(r'<!--.*?-->', '', content, flags=re.S)
    fingerprint = hashlib.sha256(json.dumps([sorted(set(links)), ' '.join(content.split())], ensure_ascii=False).encode()).hexdigest()
    return {'edition': edition, 'url': url, 'fingerprint': fingerprint}


def points_archive(blob, today):
    stamp = today.strftime('%Y%m%d')
    with ZipFile(io.BytesIO(blob)) as z:
        files = [f for f in z.infolist() if re.fullmatch(r's_ALL\d{8}\.csv', f.filename, re.I)]
        if len(files) != 1 or files[0].file_size > 35_000_000:
            raise ValueError('Unexpected full master archive')
        with z.open(files[0]) as f:
            rows = list(csv.reader(io.TextIOWrapper(f, encoding='cp932', newline='')))
    if len(rows) < 8_000 or len({len(r) for r in rows}) != 1 or len(rows[0]) < 117:
        raise ValueError('Unexpected CSV schema or row count')
    records, deferred = {}, []
    for r in rows:
        kind = r[84]
        if (kind, r[89], r[90]) not in {('G', '2', '06'), ('J', '2', '09'), ('K', '2', '10'), ('L', '2', '11')}:
            continue
        # #3: 現点数（プラス）. #85,92,93: 区分. #87,88: 適用・廃止. #113: 基本漢字名称.
        if (r[1] != 'S' or r[10] != '3' or not re.fullmatch(r'\d{3}', r[91])
                or not re.fullmatch(r'\d{2}', r[92]) or not re.fullmatch(r'\d{3}', r[93])
                or not re.fullmatch(r'\d{9}', r[2]) or not r[112].strip()):
            continue
        if not (re.fullmatch(r'\d{8}', r[86]) and re.fullmatch(r'\d{8}', r[87])):
            raise ValueError('Invalid fee master dates')
        if r[87] < stamp:
            continue
        code = kind + r[91] + (f'-{int(r[92])}' if int(r[92]) else '')
        point = Decimal(r[11])
        if not point.is_finite() or point <= 0:
            continue
        if r[86] > stamp:
            deferred.append(code)
            continue
        name = unicodedata.normalize('NFKC', r[112].strip())
        item = int(r[93])
        row = [item, name, int(point) if point == int(point) else float(point), r[2], r[87]]
        records.setdefault(code, []).append(row)
    if len(records) < 800 or not {'K000', 'K046', 'J122', 'G010', 'L100'} <= records.keys():
        raise ValueError('G/J/K/L output incomplete; previous snapshot retained')
    return {k: sorted(v) for k, v in sorted(records.items())}, sorted(set(deferred))


def updated_notice(old, new, previous_stamp, stamp):
    if old and old.get('fingerprint') == new['fingerprint']:
        return {**new, 'review': old.get('review', False) if previous_stamp >= stamp else False}
    return {**new, 'review': bool(old)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--archive', type=Path, help='Local copy of the selected official ZIP')
    ap.add_argument('--output', type=Path, default=OUT)
    args = ap.parse_args()
    today = datetime.now(timezone(timedelta(hours=9))).date()
    old = json.loads(args.output.read_text(encoding='utf-8')) if args.output.exists() else {}
    stamp, url = latest_master(download(MASTER).decode('utf-8-sig'), today)
    if old.get('version', '') > stamp.isoformat():
        raise ValueError('Official listing predates last accepted master')
    if args.archive and args.archive.name != urlsplit(url).path.rsplit('/', 1)[-1]:
        raise ValueError('Local ZIP name must match the selected official release')
    blob = args.archive.read_bytes() if args.archive else download(url)
    with ZipFile(io.BytesIO(blob)) as z:
        if urlsplit(url).path.rsplit('/', 1)[-1].replace('.zip', '.csv') not in z.namelist():
            raise ValueError('ZIP and CSV version mismatch')
    records, deferred = points_archive(blob, today)
    new = {'schema': 1, 'version': stamp.isoformat(), 'masterSource': url,
           'notice': updated_notice(old.get('notice'), notice_info(), old.get('version', ''), stamp.isoformat()),
           'deferred': deferred, 'codes': records}
    if old.get('codes') and len(records) < len(old['codes']) * 0.9:
        raise ValueError('Unexpected loss of K/J codes; previous snapshot retained')
    # Keep the activation date stable if the official data has not changed.
    comparable_old = {k: v for k, v in old.items() if k != 'appliedAsOf'}
    if new != comparable_old:
        new['appliedAsOf'] = today.isoformat()
        tmp = args.output.with_suffix('.tmp')
        tmp.write_text(json.dumps(new, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
        tmp.replace(args.output)
    print(f'{stamp}: {len(records)} codes / {sum(map(len, records.values()))} positive point rows; {len(deferred)} future-effective codes')


if __name__ == '__main__':
    main()
