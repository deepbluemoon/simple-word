"""데이터 기간·부처별 표 (docs/T5_RESULTS.md): 문서·문장·교사 짝·통과 짝 수.

`python -m training.stats [--data data] [--by half|quarter|month]`  → 마크다운 표
"""
import argparse, collections, json
from pathlib import Path

NAMES = {"mois": "행정안전부", "mohw": "보건복지부", "moe": "교육부", "msit": "과학기술정보통신부", "mss": "중소벤처기업부"}


def period(date, by):
    y, m = date[:4], int(date[5:7])
    return {"month": f"{y}-{m:02d}", "quarter": f"{y} Q{(m - 1) // 3 + 1}", "half": f"{y} H{1 if m <= 6 else 2}"}[by]


def table(data_dir="data", by="half"):
    d = Path(data_dir)
    docs = {r["id"]: r for r in map(json.loads, (d / "docs.jsonl").open(encoding="utf-8"))}
    key = lambda doc_id: (docs[doc_id]["source"], period(docs[doc_id]["published_at"], by))
    c = collections.defaultdict(collections.Counter)
    for r in docs.values():
        c[key(r["id"])]["docs"] += 1
    for r in map(json.loads, (d / "sentences.jsonl").open(encoding="utf-8")):
        c[key(r["doc_id"])]["sentences"] += 1
    for r in map(json.loads, (d / "pairs.jsonl").open(encoding="utf-8")):
        if r["doc_id"] in docs:
            c[key(r["doc_id"])]["pairs"] += 1
            c[key(r["doc_id"])]["passed"] += bool(r.get("passed"))
    rows = ["| 부처 | 기간 | 문서 | 문장 | 교사 짝 | 통과 짝 |", "|---|---|---:|---:|---:|---:|"]
    total = collections.Counter()
    for (src, per), v in sorted(c.items(), key=lambda kv: (kv[0][0], kv[0][1]), reverse=False):
        rows.append(f"| {NAMES.get(src, src)} | {per} | {v['docs']:,} | {v['sentences']:,} | {v['pairs']:,} | {v['passed']:,} |")
        total.update(v)
    rows.append(f"| **합계** | | **{total['docs']:,}** | **{total['sentences']:,}** | **{total['pairs']:,}** | **{total['passed']:,}** |")
    return "\n".join(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    ap.add_argument("--by", choices=["half", "quarter", "month"], default="half")
    a = ap.parse_args()
    print(table(a.data, a.by))
