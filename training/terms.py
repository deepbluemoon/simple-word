"""공공 용어 원본을 정규화해 {어려운 말: {alternatives, sources}}로 합친다."""
import csv, io, json, re, unicodedata, urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from simple_word.terms import found, preserve_terms  # noqa: F401

NIKL_META = ("https://www.data.go.kr/tcs/dss/selectFileDataDownload.do?publicDataPk=15130006"
             "&publicDataDetailPk=uddi:965e39a6-8b5f-4eb1-aeb2-8d8a2122147c&fileDetailSn=1")
NIKL_FILE = "https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId={id}&fileDetailSn=1"
LAW_SOURCE = "법제처_법령정보지식베이스"
TOO_GENERAL = {"가능", "관련", "기타", "내용", "대상", "사항", "사실", "사유", "이하", "이상", "이전", "이후", "자기", "해당"}


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "simple-word-collector/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def _term(value):
    return unicodedata.normalize("NFC", value or "").strip().strip("'\"“”‘’")


def _add(out, hard, alternatives, source, aliases=()):
    alts = list(dict.fromkeys(value for a in alternatives
                             if (value := _term(re.sub(r"\(.*?\)", "", a)))))
    if not alts:
        return
    for value in (hard, *aliases):
        key = _term(value)
        if len(key) < 2 or key in TOO_GENERAL or not key:
            continue
        entry = out.setdefault(key, {"alternatives": [], "sources": []})
        entry["alternatives"] = list(dict.fromkeys([*entry["alternatives"], *alts]))
        entry["sources"] = list(dict.fromkeys([*entry["sources"], *([source] if source else [])]))


def parse_nikl(text):
    out = {}
    for row in csv.DictReader(io.StringIO(text)):
        alts = (row.get("대안어(안)") or "").split(",")
        aliases = (row.get("이표기_오표기") or "").split(",")
        _add(out, row.get("단어_용어"), alts, "국립국어원_15130006", aliases)
    return out


SYNONYM = "140301"  # 법제처 용어관계코드: 동의어. 상위어·하위어·연관어·반의어는 바꿔 쓸 말이 아니라서 사전에 넣지 않는다.


def parse_law_xml(text):
    """법제처 연계 응답을 읽는다.
    - lstrmRltService(법령용어 → 일상용어), dlytrmRltService(일상용어 → 법령용어): 용어관계가 동의어인 것만
      {법령용어: 일상용어}로 넣는다.
    - 그 밖의 XML: 한 항목에 법령용어명·일상용어명이 하나씩 있으면 짝으로 본다(보관 XML 호환)."""
    root, out = ET.fromstring(text), {}

    def local(tag):
        return tag.rsplit("}", 1)[-1]

    def child(node, name):
        return next(((c.text or "").strip() for c in node if local(c.tag) == name), "")

    kind = local(root.tag)
    if kind in ("lstrmRltService", "dlytrmRltService"):
        head, own, other = ("법령용어", "법령용어명", "일상용어명") if kind == "lstrmRltService" else ("일상용어", "일상용어명", "법령용어명")
        for node in root.iter():
            if local(node.tag) != head:
                continue
            name = child(node, own)
            for link in (c for c in node if local(c.tag) == "연계용어"):
                if child(link, "용어관계코드") != SYNONYM or not (pair := child(link, other)) or pair == name:
                    continue
                hard, easy = (name, pair) if kind == "lstrmRltService" else (pair, name)
                _add(out, hard, [easy], LAW_SOURCE)
        return out
    names = {"hard": {"법령용어명", "법령용어명_한글", "lstrmNm"},
             "easy": {"일상용어명", "dlytrmNm"}}
    for node in root.iter():
        fields = [(local(c.tag), (c.text or "").strip()) for c in node.iter() if c is not node]
        hard = {value for name, value in fields if name in names["hard"] and value}
        easy = {value for name, value in fields if name in names["easy"] and value}
        if len(hard) == len(easy) == 1:
            hard, easy = next(iter(hard)), next(iter(easy))
            _add(out, hard, [easy], LAW_SOURCE)
    return out


# ---------- 법제처 Open API (용어별 조회) ----------
LAW_API = "https://www.law.go.kr/DRF/lawService.do"
LAW_TARGETS = ("lstrmRlt", "dlytrmRlt")  # 법령용어→일상용어, 일상용어→법령용어
LAW_DELAY = 1.1
JOSA = re.compile(r"(?:으로써|으로서|에서는|에게는|으로는|이라는|에서|에게|으로|부터|까지|처럼|보다|이며|이고|라는|"
                  r"하는|하고|하여|하면|해야|했다|한다|된다|되는|에는|과의|와의|은|는|이|가|을|를|의|에|와|과|도|만|로|며)$")


class LawAuthError(RuntimeError):
    pass


def law_key(root=Path(__file__).resolve().parents[1]):
    """LAW_OC: 환경변수 또는 저장소 루트 .env (값은 출력·로그에 남기지 않는다)."""
    import os

    if key := os.environ.get("LAW_OC"):
        return key
    for env in (root / ".env", Path.home() / "simple-word" / ".env"):
        if env.is_file():
            for line in env.read_text(encoding="utf-8").splitlines():
                if m := re.match(r"\s*LAW_OC\s*=\s*['\"]?([^'\"\s]+)", line):
                    return m.group(1)
    return None


def candidate_words(texts, min_count=2, limit=None):
    """원문에서 조회할 후보 낱말: 한글 2~8글자 어절에서 조사·어미를 떼고, min_count번 이상 나온 것을 많이 나온 순으로."""
    import collections

    c = collections.Counter()
    for t in texts:
        for w in re.findall(r"[가-힣]{2,12}", t):
            w = JOSA.sub("", w)
            if 2 <= len(w) <= 8 and w not in TOO_GENERAL:
                c[w] += 1
    words = [w for w, n in c.most_common() if n >= min_count]
    return words[:limit] if limit else words


def _law_get(target, query, key):
    import urllib.parse

    url = f"{LAW_API}?" + urllib.parse.urlencode({"OC": key, "target": target, "type": "XML", "query": query})
    return _get(url).decode("utf-8", errors="replace")


def fetch_law_terms(words, data_dir="data", key=None, targets=LAW_TARGETS, get=_law_get, delay=LAW_DELAY, log=print):
    """용어별로 법제처 연계 API를 불러 data/law_cache.jsonl에 쌓는다. 이미 받은 (target, 용어)는 다시 안 받는다.
    키가 없거나 인증 오류면 받지 않고 끝낸다. 저장 전에 응답 속 링크의 OC 값을 지운다. → 새로 받은 수"""
    import time

    key = key or law_key()
    if not key:
        log("LAW_OC 없음 — 법제처 용어 받기 건너뜀 (.env 에 LAW_OC=인증값)")
        return 0
    cache = Path(data_dir) / "law_cache.jsonl"
    done = set()
    if cache.exists():
        done = {(r["target"], r["query"]) for r in map(json.loads, cache.open(encoding="utf-8"))}
    n = 0
    with cache.open("a", encoding="utf-8") as out:
        for word in words:
            for target in targets:
                if (target, word) in done:
                    continue
                for attempt in range(3):  # 네트워크 오류(시간 초과 등)는 세 번까지 다시 시도, 그래도 안 되면 이 낱말은 건너뜀
                    try:
                        text = get(target, word, key).replace(key, "***")
                        break
                    except OSError as exc:
                        log(f"법제처 조회 실패({target}, {word}): {type(exc).__name__} — 재시도 {attempt + 1}/3")
                        time.sleep(5 * (attempt + 1))
                else:
                    continue
                if "<Response>" in text[:200] and ("검증에 실패" in text or "<result>" in text):
                    msg = re.search(r"<result>(.*?)</result>", text, re.S)
                    raise LawAuthError(f"법제처 API 인증 오류: {msg.group(1).strip() if msg else '알 수 없음'} "
                                       "(LAW_OC 값과 open.law.go.kr에 등록한 IP·도메인을 확인)")
                out.write(json.dumps({"target": target, "query": word, "xml": text}, ensure_ascii=False) + "\n")
                out.flush()
                done.add((target, word))
                n += 1
                time.sleep(delay)
    return n


HANGUL_ALT = re.compile(r"^[가-힣 ]+$")
DAILY_NAME = re.compile(r"<일상용어명>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</일상용어명>", re.S)


def law_dict(data_dir="data", strict=False):
    """data/law_cache.jsonl(+ 보관 data/law_terms.xml)을 합친 법제처 사전.
    법제처 '동의어'는 양방향 동의어라 어려운 말→쉬운 말이 아니다(지원→뒷바라지, 국민→내국인, 계획→플랜).
    strict: 법령용어→일상용어(lstrmRlt) 방향만, 그 법령용어가 일상용어로도 등록돼 있으면 빼고, 대안어는 한글만 남긴다."""
    data, parts, daily = Path(data_dir), [], set()
    cache = data / "law_cache.jsonl"
    rows = list(map(json.loads, cache.open(encoding="utf-8"))) if cache.exists() else []
    if strict:
        for r in rows:
            if r["target"] == "dlytrmRlt" and "dlytrmRltService" in r["xml"][:200]:
                daily.update(n.strip() for n in DAILY_NAME.findall(r["xml"]))
    for r in rows:
        if strict and r["target"] != "lstrmRlt":
            continue
        try:
            parts.append(parse_law_xml(r["xml"]))
        except ET.ParseError:
            continue
    if (data / "law_terms.xml").exists():
        parts.append(parse_law_xml((data / "law_terms.xml").read_text(encoding="utf-8")))
    out = merge_dicts(*parts) if parts else {}
    if strict:
        out = {t: {**e, "alternatives": alts} for t, e in out.items() if t not in daily
               and (alts := [a for a in e["alternatives"] if HANGUL_ALT.match(a)])}
    return out


def merge_dicts(*dictionaries):
    out = {}
    for dictionary in dictionaries:
        for term, entry in dictionary.items():
            _add(out, term, entry["alternatives"], "", ())
            target = out.get(_term(term))
            if target:
                target["sources"] = list(dict.fromkeys([*target["sources"], *entry["sources"]]))
    return out


def difficult_terms(data_dir="data", law=None):
    """원본이 있으면 내려받고, 허용 라이선스가 확인된 로컬 출처를 합친 사전.
    law: None(기본) = 국립국어원만, "raw" = 법제처 동의어 전부 더함, "strict" = law_dict(strict=True)를 더함.
    교사·검사·평가(nikl_dict)는 기본값을 쓴다. 법제처 동의어는 측정용이다(docs/DIFFICULT_TERMS.md)."""
    data = Path(data_dir)
    nikl_path = data / "nikl_terms.csv"
    if not nikl_path.exists():
        file_id = json.loads(_get(NIKL_META))["atchFileId"]
        nikl_path.parent.mkdir(parents=True, exist_ok=True)
        nikl_path.write_bytes(_get(NIKL_FILE.format(id=file_id)))
    dictionaries = [parse_nikl(nikl_path.read_text(encoding="utf-8-sig"))]
    if law and (extra := law_dict(data, strict=law == "strict")):
        dictionaries.append(extra)
    return merge_dicts(*dictionaries)


def nikl_dict(data_dir="data"):
    """호출부 호환을 위한 이름. 반환 사전은 이제 alternatives와 sources를 함께 담는다."""
    return difficult_terms(data_dir)


def coverage(rows, terms):
    counts, covered = {}, 0
    for row in rows:
        src = row["src"]
        hits = [term for term in terms if term in src and found(term, src)]  # 부분 문자열로 먼저 거른다(정규식은 느림)
        covered += bool(hits)
        for term in hits:
            for source in terms[term]["sources"]:
                counts[source] = counts.get(source, 0) + 1
    return {"sentences": len(rows), "with_terms": covered,
            "rate": round(covered / len(rows), 4) if rows else 0.0,
            "term_hits_by_source": dict(sorted(counts.items()))}


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="통과 데이터와 평가 후보의 어려운 용어 포함률")
    ap.add_argument("--data", default="data")
    ap.add_argument("--pairs", default="data/pairs.jsonl")
    ap.add_argument("--candidates", default="data/eval/candidates.jsonl")
    ap.add_argument("--fetch-law", action="store_true",
                    help="먼저 통과 짝·평가 후보 원문의 후보 낱말을 법제처 연계 API로 조회해 data/law_cache.jsonl에 쌓는다(LAW_OC 필요)")
    ap.add_argument("--min-count", type=int, default=2, help="후보 낱말 최소 출현 수")
    ap.add_argument("--law", choices=["raw", "strict"], help="법제처 동의어를 사전에 더해 잰다(기본: 국립국어원만)")
    ap.add_argument("--limit", type=int, help="조회할 후보 낱말 수 상한(많이 나온 순)")
    args = ap.parse_args()
    read = lambda path: [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line]
    pairs = [row for row in read(args.pairs) if row.get("passed")]
    candidates = read(args.candidates)
    if args.fetch_law:
        words = candidate_words([r["src"] for r in pairs + candidates], args.min_count, args.limit)
        print(f"후보 낱말 {len(words)}개 조회")
        try:
            print("새로 받음", fetch_law_terms(words, args.data))
        except LawAuthError as exc:
            print(exc)
    terms = difficult_terms(args.data, law=args.law)
    by_source = {}
    for entry in terms.values():
        for source in entry["sources"]:
            by_source[source] = by_source.get(source, 0) + 1
    print(json.dumps({"dictionary_terms_by_source": by_source, "passed_pairs": coverage(pairs, terms),
                      "eval_candidates": coverage(candidates, terms)}, ensure_ascii=False, indent=2))
