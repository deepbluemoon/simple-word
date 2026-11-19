"""보존 용어 목록과 국립국어원 '쉽고 바른 공공언어 쓰기 평가용 용어 목록'(data.go.kr 15130006, 공공누리 제1유형)."""
import csv, io, json, re, urllib.request
from pathlib import Path

from simple_word.terms import found, preserve_terms  # noqa: F401  (서빙과 같은 목록·함수)

NIKL_META = ("https://www.data.go.kr/tcs/dss/selectFileDataDownload.do?publicDataPk=15130006"
             "&publicDataDetailPk=uddi:965e39a6-8b5f-4eb1-aeb2-8d8a2122147c&fileDetailSn=1")
NIKL_FILE = "https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId={id}&fileDetailSn=1"


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "simple-word-collector/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def nikl_dict(data_dir="data"):
    """{용어 또는 이표기: [대안어,...]}. 처음 한 번 data/nikl_terms.csv 로 내려받는다."""
    path = Path(data_dir) / "nikl_terms.csv"
    if not path.exists():
        file_id = json.loads(_get(NIKL_META))["atchFileId"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_get(NIKL_FILE.format(id=file_id)))
    return parse_nikl(path.read_text(encoding="utf-8-sig"))


def parse_nikl(text):
    out = {}
    for row in csv.DictReader(io.StringIO(text)):
        alts = [re.sub(r"\(.*?\)", "", a).strip() for a in row["대안어(안)"].split(",")]
        alts = [a for a in alts if a]
        for key in [row["단어_용어"], *row["이표기_오표기"].split(",")]:
            if key.strip() and alts:
                out[key.strip()] = alts
    return out
