"""부처 보도자료 수집: RSS(새 글) + 게시판 목록(과거 글) → raw/<날짜>/<id>.html, docs.jsonl.

크론: `python -m training.collect`
과거 글 채우기: `python -m training.collect --backfill-pages 300 --since 2024-11-01` (목록을 거슬러 올라가다 한 쪽의 글이 모두 since보다 옛날이면 그 부처는 멈춤)
부처 고르기: `--sources mois,mohw,moe`
이미 받은 URL·같은 본문 해시는 건너뛴다(여러 번 돌려도 결과 같음). 요청 간격 1초 이상.
교육부(moe)는 본문이 HTML에 없고 첨부 HWPX에만 있어 첨부를 받아 글자를 뽑는다.
data.go.kr 보도자료 OpenAPI는 training/datagokr.py (serviceKey 필요).
"""
import argparse, datetime as dt, hashlib, io, json, re, time, urllib.request, zipfile
from xml.etree import ElementTree
from html.parser import HTMLParser
from pathlib import Path

UA = "simple-word-collector/0.1"
DELAY = 1.1
KST = dt.timezone(dt.timedelta(hours=9))

# 복지부 robots.txt는 /board.es 를 막고 mid=a10503010100&bid=0027 만 허용 → 그 경로만 쓴다.
SOURCES = {
    "mois": {
        "rss": "https://www.mois.go.kr/gpms/view/jsp/rss/rss.jsp?ctxCd=1012",
        "list": "https://www.mois.go.kr/frt/bbs/type010/commonSelectBoardList.do?bbsId=BBSMSTR_000000000008&pageIndex={page}",
        "id_re": r"type010/commonSelectBoardArticle\.do[^\"'<]*?bbsId=BBSMSTR_000000000008&(?:amp;)?nttId=(\d+)",
        "article": "https://www.mois.go.kr/frt/bbs/type010/commonSelectBoardArticle.do?bbsId=BBSMSTR_000000000008&nttId={id}",
        "body": ('id="desc_pc"', 'id="desc_mo"'),
    },
    "mohw": {
        "rss": "https://www.mohw.go.kr/rss/board.es?mid=a10503000000&bid=0027",
        "list": "https://www.mohw.go.kr/board.es?mid=a10503010100&bid=0027&nPage={page}",
        "id_re": r"bid=0027&(?:amp;)?(?:act=view&(?:amp;)?)?list_no=(\d+)",
        "article": "https://www.mohw.go.kr/board.es?mid=a10503010100&bid=0027&act=view&list_no={id}",
        "body": ('class="board_view"', "첨부파일"),
    },
    # 교육부: robots.txt는 /search 만 막음. 글마다 공공누리 제1유형 표시(img_opentype01). 본문은 첨부 HWPX.
    "moe": {
        "rss": None,  # RSS 대신 목록 1쪽
        "list": "https://www.moe.go.kr/boardCnts/listRenew.do?type=default&page={page}&m=020402&s=moe&boardID=294",
        "id_re": r"goView\('294',\s*'(\d+)'",
        "article": "https://www.moe.go.kr/boardCnts/viewRenew.do?boardID=294&boardSeq={id}&lev=0&m=020402&s=moe",
        "hwpx": "https://www.moe.go.kr/boardCnts/fileDown.do?m=020402&s=moe&fileSeq={seq}",
    },
}
# 넣지 않은 부처 (2026-11-19 확인, docs/T5_RESULTS.md):
# - 고용노동부: 저작권정책상 "제1유형을 부착하여 개방"한 것만 자유 이용인데 보도자료 본문에 표시가 없음
# - 국토교통부: 본문이 HTML에 없고, 안내 문구에 공공누리 유형이 없음
# - 정책브리핑(korea.kr): RSS 중단 사유가 저작권 → 쓰지 않음
MAX_HWPX = 20 * 2**20

_last = 0.0


def fetch_bytes(url, max_bytes=None):
    global _last
    time.sleep(max(0.0, _last + DELAY - time.time()))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read(max_bytes + 1 if max_bytes else -1)
            if max_bytes and len(data) > max_bytes:
                raise ValueError(f"too large: {url}")
            return data
    finally:
        _last = time.time()


def fetch(url):
    return fetch_bytes(url).decode("utf-8", errors="replace")


def hwpx_text(data):
    """HWPX(zip) → 문단 글자. Contents/section*.xml 의 <hp:p> 안 <hp:t>."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        if sum(i.file_size for i in z.infolist()) > MAX_HWPX:
            raise ValueError("hwpx unpacked too large")
        paras = []
        for name in sorted(n for n in z.namelist() if n.startswith("Contents/section") and n.endswith(".xml")):
            root = ElementTree.fromstring(z.read(name))
            for p in root.iter():
                if p.tag.rsplit("}", 1)[-1] != "p":
                    continue
                t = "".join(x.text or "" for x in p.iter() if x.tag.rsplit("}", 1)[-1] == "t")
                if t.strip() and not any(c.tag.rsplit("}", 1)[-1] == "p" for c in p.iter() if c is not p):
                    paras.append(t.strip())
    head = [i for i, l in enumerate(paras[:15]) if re.match(r"^(?:보도자료|배포|보도시점|\(인터넷\)|\(지\s*면\)|보도|일시)", l)]
    return "\n".join(paras[head[-1] + 1 :] if head else paras)  # 머리 표(보도자료·배포·보도시점)는 본문이 아님


class _Text(HTMLParser):
    BLOCK = {"p", "div", "br", "li", "tr", "td", "h1", "h2", "h3", "h4", "table", "ul", "ol", "section", "article"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        self.skip += tag in ("script", "style")
        if tag in self.BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        self.skip -= tag in ("script", "style") and self.skip > 0
        if tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, d):
        if not self.skip:
            self.out.append(d)


def html_text(html):
    p = _Text()
    p.feed(html)
    lines = (re.sub(r"[ \t 　]+", " ", l).strip() for l in "".join(p.out).split("\n"))
    return "\n".join(l for l in lines if l)


def parse_moe(html):
    """교육부 글 → (title, published_at|None, 첫 HWPX fileSeq|None, license)."""
    m = re.search(r'class="news-header"[^>]*>\s*<h3>(.*?)</h3>', html, re.S)
    title = html_text(m.group(1)) if m else ""
    d = re.search(r'class="reg-date">\s*(\d{4})-(\d{2})-(\d{2})', html)
    seq = None
    for item in re.findall(r"<li>(.*?)</li>", html[html.find('class="attachment"'):], re.S):
        if ".hwpx" in item and (f := re.search(r"fileDown\.do\?[^\"']*fileSeq=([0-9a-f]+)", item)):
            seq = f.group(1)
            break
    lic = "KOGL-1" if "img_opentype01" in html or "licenseType1.do" in html else "unknown"
    return title, f"{d[1]}-{d[2]}-{d[3]}" if d else None, seq, lic


def parse_article(source, html):
    """원문 HTML → (title, published_at|None, body, license). 본문은 정제 전 텍스트."""
    start, end = SOURCES[source]["body"]
    i = html.find(start)
    body = ""
    if i >= 0:
        i = html.find(">", i) + 1
        j = html.find(end, i)
        body = html_text(html[i : j if j > 0 else None])
    m = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]*)"', html) or re.search(r"<title>([^<]*)</title>", html)
    title = re.split(r"\s+\|\s+|\s+<\s+", html_text(m.group(1)))[0] if m else ""
    d = re.search(r"(?:등록일|작성일)\s*:\s*(\d{4})[.-](\d{2})[.-](\d{2})", html_text(html))
    published = f"{d[1]}-{d[2]}-{d[3]}" if d else None
    lic = "KOGL-1" if re.search(r"공공누리\s*(?:제\s*)?1\s*유형", html) else "unknown"
    if source == "mohw" and body:  # board_view 안의 제목·작성일·담당자 줄은 본문이 아님
        lines = body.split("\n")
        k = max((n for n, l in enumerate(lines[:12]) if l.startswith("담당부서")), default=-1)
        body = "\n".join(lines[k + 2 :] if k >= 0 else lines)  # 담당부서 줄 + 값 줄 건너뜀
    return title, published, body, lic


def ids_in(source, html):
    return list(dict.fromkeys(re.findall(SOURCES[source]["id_re"], html)))


def load_seen(docs_path):
    urls, hashes = set(), set()
    if docs_path.exists():
        for line in docs_path.open(encoding="utf-8"):
            d = json.loads(line)
            urls.add(d["url"])
            if d["body"]:
                hashes.add(hashlib.sha1(d["body"].encode()).hexdigest())
    return urls, hashes


def read_article(source, url, log=print):
    """→ (html, title, published, body, license). 교육부는 첨부 HWPX에서 본문을 뽑는다."""
    html = fetch(url)
    if source != "moe":
        return (html, *parse_article(source, html))
    title, published, seq, lic = parse_moe(html)
    body = ""
    if seq:
        try:
            body = hwpx_text(fetch_bytes(SOURCES["moe"]["hwpx"].format(seq=seq), MAX_HWPX))
        except (ValueError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
            log(f"hwpx 읽기 실패 {url}: {exc}")
    return html, title, published, body, lic


def collect(data_dir, raw_dir, backfill_pages=0, limit=None, log=print, sources=None, since=None):
    """backfill_pages: 정수(모든 부처) 또는 {부처: 쪽 수}. since: 'YYYY-MM-DD' — 목록 한 쪽에서 새로 받은 글이
    모두 이 날보다 옛날이면 그 부처의 과거 글 채우기를 멈춘다."""
    data_dir, raw_dir = Path(data_dir), Path(raw_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    docs_path = data_dir / "docs.jsonl"
    urls, hashes = load_seen(docs_path)
    added = 0
    with docs_path.open("a", encoding="utf-8") as out:
        for source in sources or SOURCES:
            cfg = SOURCES[source]
            n_pages = backfill_pages.get(source, 0) if isinstance(backfill_pages, dict) else backfill_pages
            pages = ([cfg["rss"]] if cfg.get("rss") else []) + [cfg["list"].format(page=p) for p in range(1, max(n_pages, 0 if cfg.get("rss") else 1) + 1)]
            for page_url in pages:
                if limit is not None and added >= limit:
                    return added
                new_ids = [i for i in ids_in(source, fetch(page_url)) if cfg["article"].format(id=i) not in urls]
                dates = []
                for aid in new_ids:
                    if limit is not None and added >= limit:
                        return added
                    url = cfg["article"].format(id=aid)
                    html, title, published, body, lic = read_article(source, url, log)
                    now = dt.datetime.now(KST)
                    dates.append(published)
                    urls.add(url)
                    h = hashlib.sha1(body.encode()).hexdigest()
                    if body and h in hashes:
                        log(f"skip duplicate body {url}")
                        continue
                    hashes.add(h)
                    doc_id = f"{source}-{aid}"
                    raw = raw_dir / now.strftime("%Y-%m-%d") / f"{doc_id}.html"
                    raw.parent.mkdir(parents=True, exist_ok=True)
                    raw.write_text(html, encoding="utf-8")
                    doc = {"id": doc_id, "url": url, "source": source, "published_at": published or now.isoformat(timespec="seconds"),
                           "title": title, "body": body, "fetched_at": now.isoformat(timespec="seconds"), "license": lic}
                    if not published:
                        doc["published_at_missing"] = True  # 게시일 없음 → 수집 시각으로 대신하고 표시
                    out.write(json.dumps(doc, ensure_ascii=False) + "\n")
                    out.flush()
                    added += 1
                    log(f"+ {doc_id} {published} {title[:40]}")
                if since and dates and all(d and d < since for d in dates) and page_url != cfg.get("rss"):
                    log(f"{source}: {page_url} 의 글이 모두 {since} 이전 → 멈춤")
                    break
    return added


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    ap.add_argument("--raw", default="raw")
    ap.add_argument("--backfill-pages", type=int, default=0, help="게시판 목록 1..N 페이지를 거슬러 올라감")
    ap.add_argument("--limit", type=int, help="새로 받을 문서 최대 수")
    ap.add_argument("--sources", help="쉼표로 구분 (기본: 전부). " + ",".join(SOURCES))
    ap.add_argument("--since", help="YYYY-MM-DD: 이보다 옛날 쪽에 닿으면 그 부처는 멈춤")
    a = ap.parse_args()
    print("added", collect(a.data, a.raw, a.backfill_pages, a.limit, sources=a.sources.split(",") if a.sources else None, since=a.since))
