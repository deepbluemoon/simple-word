"""행안부·복지부 보도자료 수집: RSS(새 글) + 게시판 목록(과거 글) → raw/<날짜>/<id>.html, docs.jsonl.

크론: `python -m training.collect`  /  과거 글 한 번 채우기: `python -m training.collect --backfill-pages 200`
이미 받은 URL·같은 본문 해시는 건너뛴다(여러 번 돌려도 결과 같음). 요청 간격 1초 이상.
"""
import argparse, datetime as dt, hashlib, json, re, time, urllib.request
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
}

_last = 0.0


def fetch(url):
    global _last
    time.sleep(max(0.0, _last + DELAY - time.time()))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", errors="replace")
    finally:
        _last = time.time()


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


def collect(data_dir, raw_dir, backfill_pages=0, limit=None, log=print):
    data_dir, raw_dir = Path(data_dir), Path(raw_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    docs_path = data_dir / "docs.jsonl"
    urls, hashes = load_seen(docs_path)
    added = 0
    with docs_path.open("a", encoding="utf-8") as out:
        for source, cfg in SOURCES.items():
            pages = [cfg["rss"]] + [cfg["list"].format(page=p) for p in range(1, backfill_pages + 1)]
            for page_url in pages:
                if limit is not None and added >= limit:
                    return added
                new_ids = [i for i in ids_in(source, fetch(page_url)) if cfg["article"].format(id=i) not in urls]
                for aid in new_ids:
                    if limit is not None and added >= limit:
                        return added
                    url = cfg["article"].format(id=aid)
                    html = fetch(url)
                    now = dt.datetime.now(KST)
                    title, published, body, lic = parse_article(source, html)
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
    return added


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    ap.add_argument("--raw", default="raw")
    ap.add_argument("--backfill-pages", type=int, default=0, help="게시판 목록 1..N 페이지를 거슬러 올라감")
    ap.add_argument("--limit", type=int, help="새로 받을 문서 최대 수")
    a = ap.parse_args()
    print("added", collect(a.data, a.raw, a.backfill_pages, a.limit))
