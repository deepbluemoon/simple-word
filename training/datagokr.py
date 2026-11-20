"""data.go.kr 부처 보도자료 OpenAPI 수집 (docs/DATA_RESEARCH.md 3절). 이용허락범위 "제한 없음".

키: 환경변수 또는 저장소 루트 .env 의 DATA_GO_KR_KEY (사용자가 발급 예정). 키가 없으면 아무것도 받지 않고 끝낸다.

    python -m training.datagokr --api msit --pages 5

[미확인] 키가 없어 실제 응답 형식을 아직 보지 못했다. 응답 항목 이름은 흔한 후보(FIELDS)에서 고른다.
키를 받으면 --dump 로 응답 하나를 먼저 저장해 보고 FIELDS·APIS를 맞춘다.
"""
import argparse, datetime as dt, hashlib, json, os, re, urllib.parse
from pathlib import Path

from training.collect import KST, fetch, html_text, load_seen

APIS = {  # 이름: (엔드포인트, 출처 표시용 기관)
    "msit": ("https://apis.data.go.kr/1721000/msitpressreleaseinfo/pressReleaseList", "과학기술정보통신부"),
    "mss": ("https://apis.data.go.kr/1421000/mssPressService_v2/getPressList", "중소벤처기업부"),  # 오퍼레이션명 [미확인]
}
FIELDS = {
    "id": ("id", "seq", "itemId", "nttId", "boardSeq", "pressSeq", "contentId"),
    "title": ("title", "subject", "sj", "nttSj", "pressTitle"),
    "body": ("content", "contents", "cn", "nttCn", "body", "pressContent", "dataContents"),
    "date": ("date", "regDate", "registDt", "pubDate", "writeDate", "frstRegistPnttm", "approveDate"),
    "url": ("url", "link", "viewUrl", "originUrl"),
}
LICENSE = "DATAGOKR-free"  # 공공데이터포털 이용허락범위 제한 없음 (preprocess가 KOGL-1과 같이 받는다)


def api_key(root=Path(__file__).resolve().parents[1]):
    if key := os.environ.get("DATA_GO_KR_KEY"):
        return key
    env = root / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            if m := re.match(r"\s*DATA_GO_KR_KEY\s*=\s*['\"]?([^'\"\s]+)", line):
                return m.group(1)
    return None


def pick(item, name):
    for k in FIELDS[name]:
        if item.get(k) not in (None, ""):
            return str(item[k])
    return None


def items_of(payload):
    """data.go.kr 흔한 모양: response.body.items.item (list|dict), 또는 최상위 items/data 목록."""
    node = payload.get("response", payload)
    node = node.get("body", node)
    items = node.get("items", node.get("data", []))
    if isinstance(items, dict):
        items = items.get("item", [])
    return [items] if isinstance(items, dict) else list(items)


def to_doc(api, item, now):
    title, body = pick(item, "title") or "", html_text(pick(item, "body") or "")
    raw_id = pick(item, "id") or hashlib.sha1((title + body).encode()).hexdigest()[:12]
    d = re.search(r"(\d{4})[.-]?(\d{2})[.-]?(\d{2})", pick(item, "date") or "")
    doc = {"id": f"{api}-{raw_id}", "url": pick(item, "url") or f"{APIS[api][0]}#{raw_id}", "source": api,
           "published_at": f"{d[1]}-{d[2]}-{d[3]}" if d else now.isoformat(timespec="seconds"), "title": title, "body": body,
           "fetched_at": now.isoformat(timespec="seconds"), "license": LICENSE, "attribution": APIS[api][1]}
    if not d:
        doc["published_at_missing"] = True
    return doc


def collect_api(api, data_dir="data", pages=1, rows=100, key=None, dump=None, log=print):
    key = key or api_key()
    if not key:
        log("DATA_GO_KR_KEY 없음 — data.go.kr 수집 건너뜀")
        return 0
    data_dir = Path(data_dir)
    docs_path = data_dir / "docs.jsonl"
    urls, hashes = load_seen(docs_path)
    added = 0
    with docs_path.open("a", encoding="utf-8") as out:
        for page in range(1, pages + 1):
            q = urllib.parse.urlencode({"serviceKey": key, "pageNo": page, "numOfRows": rows, "returnType": "json", "type": "json"})
            text = fetch(f"{APIS[api][0]}?{q}")
            if dump:
                Path(dump).write_text(text, encoding="utf-8")
            items = items_of(json.loads(text))
            if not items:
                break
            now = dt.datetime.now(KST)
            for item in items:
                doc = to_doc(api, item, now)
                h = hashlib.sha1(doc["body"].encode()).hexdigest()
                if doc["url"] in urls or (doc["body"] and h in hashes):
                    continue
                urls.add(doc["url"])
                hashes.add(h)
                out.write(json.dumps(doc, ensure_ascii=False) + "\n")
                added += 1
    return added


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", choices=sorted(APIS), required=True)
    ap.add_argument("--data", default="data")
    ap.add_argument("--pages", type=int, default=1)
    ap.add_argument("--rows", type=int, default=100)
    ap.add_argument("--dump", help="첫 응답 원문을 이 파일에 저장 (형식 확인용)")
    a = ap.parse_args()
    print("added", collect_api(a.api, a.data, a.pages, a.rows, dump=a.dump))
