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


def parse_law_xml(text):
    """법제처 lstrmRlt 응답·보관 XML의 법령용어와 일상용어 연계를 읽는다."""
    root, out = ET.fromstring(text), {}
    names = {"hard": {"법령용어명", "법령용어명_한글", "lstrmNm"},
             "easy": {"일상용어명", "dlytrmNm"}}
    def local(tag):
        return tag.rsplit("}", 1)[-1]
    for node in root.iter():
        fields = [(local(child.tag), (child.text or "").strip()) for child in node.iter() if child is not node]
        hard = {value for name, value in fields if name in names["hard"] and value}
        easy = {value for name, value in fields if name in names["easy"] and value}
        if len(hard) == len(easy) == 1:
            hard, easy = next(iter(hard)), next(iter(easy))
            _add(out, hard, [easy], LAW_SOURCE)
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


def difficult_terms(data_dir="data"):
    """원본이 있으면 내려받고, 허용 라이선스가 확인된 로컬 출처를 합친 사전."""
    data = Path(data_dir)
    nikl_path = data / "nikl_terms.csv"
    if not nikl_path.exists():
        file_id = json.loads(_get(NIKL_META))["atchFileId"]
        nikl_path.parent.mkdir(parents=True, exist_ok=True)
        nikl_path.write_bytes(_get(NIKL_FILE.format(id=file_id)))
    dictionaries = [parse_nikl(nikl_path.read_text(encoding="utf-8-sig"))]
    law_path = data / "law_terms.xml"
    if law_path.exists():
        dictionaries.append(parse_law_xml(law_path.read_text(encoding="utf-8")))
    return merge_dicts(*dictionaries)


def nikl_dict(data_dir="data"):
    """호출부 호환을 위한 이름. 반환 사전은 이제 alternatives와 sources를 함께 담는다."""
    return difficult_terms(data_dir)


def coverage(rows, terms):
    counts, covered = {}, 0
    for row in rows:
        src, hits = row["src"], [term for term in terms if found(term, row["src"])]
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
    args = ap.parse_args()
    terms = difficult_terms(args.data)
    read = lambda path: [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line]
    pairs = [row for row in read(args.pairs) if row.get("passed")]
    candidates = read(args.candidates)
    print(json.dumps({"passed_pairs": coverage(pairs, terms), "eval_candidates": coverage(candidates, terms)},
                     ensure_ascii=False, indent=2))
