"""docs.jsonl → sentences.jsonl (+ drops.jsonl, stats.jsonl). 매번 docs.jsonl 전체에서 다시 만든다(결과 같음).

`python -m training.preprocess`
"""
import argparse, collections, datetime as dt, json, re, unicodedata
from pathlib import Path

PII = [  # 순서 중요: 주민번호가 전화번호 형식에 먼저 걸리지 않게
    (re.compile(r"\b\d{6}-?[1-8]\d{6}\b"), "[주민번호]"),
    (re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), "[이메일]"),
    (re.compile(r"(?<!\d)(?:\+82[- ]?)?0\d{1,2}[)\s.-]*\d{3,4}[\s.-]*\d{4}(?!\d)"), "[전화]"),
]
STOP_LINE = re.compile(r"^\W*(?:(?:담당\s*자|담당\s*부서|문의처?)\s*[:：]|붙\s*임\b)")  # 이 줄부터 끝까지 버림
ATTACH = re.compile(r"\.(?:hwpx?|pdf|docx?|xlsx?|zip|jpe?g|png)\b", re.I)
BULLET = re.compile(r"^(?:[-–―·•◦○●□■◇◆▶▷ㅇ※*]|\d+[.)]|[①-⑳])\s*")


def mask_pii(s):
    for pat, rep in PII:
        s = pat.sub(rep, s)
    return s


def clean_lines(body):
    lines = []
    for line in unicodedata.normalize("NFC", body).split("\n"):
        line = re.sub(r"\s+", " ", line).strip()
        if STOP_LINE.search(line):
            break
        if ATTACH.search(line):
            continue
        line = re.sub(r"\s*-$", "", BULLET.sub("", line)).strip()
        if line:
            lines.append(line)
    merged = []  # 쉼표로 끝난 줄은 다음 줄과 이어진 문장
    for line in lines:
        if merged and merged[-1].endswith(","):
            merged[-1] += " " + line
        else:
            merged.append(line)
    return merged


def split_sentences(body):
    out = []
    for line in clean_lines(body):
        out += [s.strip() for s in re.split(r"(?<=[.?!])\s+", mask_pii(line)) if s.strip()]
    return out


def hangul_ratio(s):
    chars = [c for c in s if not c.isspace()]
    return sum("가" <= c <= "힣" for c in chars) / max(len(chars), 1)


def reject(s, seen_exact, seen_near):
    if not 10 <= len(s) <= 200:
        return "length"
    if hangul_ratio(s) < 0.5:
        return "hangul_ratio"
    if s in seen_exact:
        return "duplicate"
    near = re.sub(r"[^가-힣]", "", s)  # 숫자·기호·띄어쓰기만 다른 문장 = 유사 중복
    if near in seen_near:
        return "near_duplicate"
    seen_exact.add(s)
    seen_near.add(near)
    return None


def preprocess(data_dir):
    data_dir = Path(data_dir)
    seen_exact, seen_near = set(), set()
    reasons = collections.Counter()
    n_docs = n_sent = 0
    with (data_dir / "sentences.jsonl").open("w", encoding="utf-8") as out, (data_dir / "drops.jsonl").open("w", encoding="utf-8") as drops:
        def drop(reason, doc_id, text=None):
            reasons[reason] += 1
            drops.write(json.dumps({"stage": "preprocess", "doc_id": doc_id, "reason": reason, "text": text}, ensure_ascii=False) + "\n")

        for line in (data_dir / "docs.jsonl").open(encoding="utf-8"):
            doc = json.loads(line)
            n_docs += 1
            if not doc["body"].strip():
                drop("doc_no_body", doc["id"])
                continue
            if doc["license"] != "KOGL-1":
                drop("doc_license", doc["id"])
                continue
            idx = 0
            for s in split_sentences(doc["body"]):
                if r := reject(s, seen_exact, seen_near):
                    drop(r, doc["id"], s)
                    continue
                out.write(json.dumps({"doc_id": doc["id"], "idx": idx, "text": s}, ensure_ascii=False) + "\n")
                idx += 1
                n_sent += 1
    stats = {"at": dt.datetime.now().isoformat(timespec="seconds"), "stage": "preprocess", "docs": n_docs,
             "sentences": n_sent, "dropped": dict(reasons),
             "sentence_drop_rate": round((d := sum(v for k, v in reasons.items() if not k.startswith("doc_"))) / max(n_sent + d, 1), 3)}
    with (data_dir / "stats.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(stats, ensure_ascii=False) + "\n")
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    print(json.dumps(preprocess(ap.parse_args().data), ensure_ascii=False))
