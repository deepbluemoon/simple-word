"""사람 검수 평가셋(이슈 #7): 후보 200건 추출 → 검수 CSV → eval_set.jsonl.

python -m training.eval_set candidates --splits data/v2 --model models/v2   # data/eval/candidates.jsonl
python -m training.eval_set export-csv                                      # data/eval/review.csv
python -m training.eval_set import-csv                                      # data/eval/eval_set.jsonl (src·ref)
python -m training.train --version v2 ... --eval-set data/eval/eval_set.jsonl --check-leakage

후보는 pairs.jsonl 문장 중 data/<v>/{train,valid,test}.jsonl·고정 parity 입력과 같거나
유사 중복(한글만 남겨 같음)인 문장을 뺀 것에서, 층(stratum)별 정해진 수만큼 seed 0으로 뽑는다.
"""
import argparse, csv, json, random
from collections import Counter
from pathlib import Path

from simple_word.numbers import numbers
from simple_word.terms import found, preserve_terms
from training.export import PARITY_INPUTS
from training.terms import nikl_dict
from training.train import _near

SEED = 0
LONG = 100  # 글자 수가 이 이상이면 '긴 문장'
# 층 이름, 뽑을 수. 한 문장이 여러 층에 해당하면 위에 있는 층(드문 것)부터 배정한다.
QUOTAS = [("preserve", 30), ("difficult", 20), ("numbers", 60), ("long", 30), ("general", 60)]
CSV_COLS = ["id", "원문", "제안 쉬운 말", "고친 쉬운 말", "메모"]


def has_term(terms, s):
    return [t for t in terms if t in s and found(t, s)]


def features(src, nikl, keep):
    return {"numbers": sorted(value for value, _, _ in numbers(src).elements()), "difficult": has_term(nikl, src),
            "preserve": has_term(keep, src), "long": len(src) >= LONG}


def stratum(f):
    if f["preserve"]:
        return "preserve"
    if f["difficult"]:
        return "difficult"
    if f["numbers"]:
        return "numbers"
    return "long" if f["long"] else "general"


def used_texts(splits_dir):
    """(학습에 쓴 문장·parity 입력의 유사 중복 키 집합, {doc_id: 분할})"""
    near, owner = {_near(p) for p in PARITY_INPUTS}, {}
    for name in ("train", "valid", "test"):
        for line in (Path(splits_dir) / f"{name}.jsonl").open(encoding="utf-8"):
            r = json.loads(line)
            near.add(_near(r["src"]))
            owner[r["doc_id"]] = name
    return near, owner


def pool(pairs_path, splits_dir, nikl, keep):
    (used, owner), seen, out = used_texts(splits_dir), set(), []
    for line in Path(pairs_path).open(encoding="utf-8"):
        p = json.loads(line)
        n = _near(p["src"])
        if not n or n in used or n in seen:
            continue
        seen.add(n)
        f = features(p["src"], nikl, keep)
        out.append({**p, "features": f, "stratum": stratum(f), "doc_split": owner.get(p["doc_id"])})
    return out


def sample(rows, quotas=QUOTAS, seed=SEED):
    """층별로 섞어 quota 만큼. 모자라면 있는 만큼(빈 자리는 general 로 채운다)."""
    rng, by = random.Random(seed), {}
    for r in rows:
        by.setdefault(r["stratum"], []).append(r)
    for v in by.values():
        rng.shuffle(v)
    picked, short = [], 0
    for name, n in quotas:
        got = by.get(name, [])[:n]
        short += n - len(got)
        picked += got
    if short:
        picked += by.get("general", [])[dict(quotas).get("general", 0):][:short]
    return picked


def candidates(a):
    nikl = nikl_dict(a.data_dir)
    keep = preserve_terms()
    rows = pool(a.pairs, a.splits, nikl, keep)
    picked = sample(rows)
    from simple_word.model import Simplifier

    simp = Simplifier(a.model)
    outs = simp.simplify_detailed([r["src"] for r in picked])
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for i, (r, (y, fb)) in enumerate(zip(picked, outs), 1):
            fh.write(json.dumps({"id": f"e{i:03d}", "doc_id": r["doc_id"], "idx": r["idx"], "stratum": r["stratum"],
                                 "doc_split": r["doc_split"], "features": r["features"], "src": r["src"], "teacher": r.get("tgt"),
                                 "teacher_passed": r.get("passed"), "teacher_reject": r.get("reject_reason"),
                                 "model": Path(a.model).name, "model_out": y, "fallback": fb}, ensure_ascii=False) + "\n")
    report = {"pool": len(rows), "pool_by_stratum": dict(Counter(r["stratum"] for r in rows)),
              "picked_by_stratum": dict(Counter(r["stratum"] for r in picked)), "picked": len(picked),
              "fallback": sum(fb for _, fb in outs),
              "picked_by_doc_split": dict(Counter(str(r["doc_split"]) for r in picked)),
              "picked_by_teacher_reject": dict(Counter(str(r.get("reject_reason")) for r in picked)), "teacher_passed": sum(bool(r.get("passed")) for r in picked),
              "out": str(out)}
    print(json.dumps(report, ensure_ascii=False, indent=1))


def suggestion(r):
    """제안 쉬운 말: v2가 원문으로 대체(fallback)했거나 원문과 같으면 교사 출력, 아니면 v2 출력."""
    y = r["model_out"]
    return r["teacher"] or y if r["fallback"] or y == r["src"] else y


def hint(r):
    """메모 칸 기본값: 제안이 어디서 왔는지. 지워도 된다('제외'로 시작하면 평가셋에서 뺀다)."""
    if r["fallback"] or r["model_out"] == r["src"]:
        why = f", 교사 검사 탈락: {r['teacher_reject']}" if r.get("teacher_reject") else ""
        return f"[제안=교사 출력. v2는 원문 그대로(fallback){why}]"
    return "[제안=v2 출력]"


def export_csv(a):
    rows = [json.loads(l) for l in Path(a.candidates).open(encoding="utf-8")]
    with Path(a.csv).open("w", encoding="utf-8-sig", newline="") as fh:  # BOM: 엑셀에서 한글 안 깨짐
        w = csv.writer(fh)
        w.writerow(CSV_COLS)
        for r in rows:
            w.writerow([r["id"], r["src"], suggestion(r), "", hint(r)])
    print(f"{len(rows)}건 → {a.csv}")


def import_csv(a):
    """고친 쉬운 말이 있으면 그것, 비어 있으면 제안 쉬운 말을 정답(ref)으로. 메모가 '제외'로 시작하면 뺀다."""
    cand = {r["id"]: r for r in map(json.loads, Path(a.candidates).open(encoding="utf-8"))}
    out, skipped, edited = [], 0, 0
    with Path(a.csv).open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            memo = (row.get("메모") or "").strip()
            if memo.startswith("제외"):
                skipped += 1
                continue
            c = cand.get(row["id"].strip())
            if c is None:
                raise SystemExit(f"후보에 없는 id: {row['id']}")
            if row["원문"].strip() != c["src"]:
                raise SystemExit(f"{row['id']}: 원문이 후보와 다릅니다(원문 열은 고치지 마세요)")
            ref = (row.get("고친 쉬운 말") or "").strip()
            edited += bool(ref)
            out.append({"id": c["id"], "src": c["src"], "ref": ref or row["제안 쉬운 말"].strip(), "edited": bool(ref),
                        "stratum": c["stratum"], "doc_id": c["doc_id"], "memo": memo})
    Path(a.out).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out), encoding="utf-8")
    print(f"{len(out)}건(고침 {edited}, 제외 {skipped}) → {a.out}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("candidates")
    c.add_argument("--pairs", default="data/pairs.jsonl")
    c.add_argument("--splits", default="data/v2", help="학습에 쓴 train/valid/test.jsonl 폴더")
    c.add_argument("--model", default="models/v2")
    c.add_argument("--data-dir", default="data", help="nikl_terms.csv 위치")
    c.add_argument("--out", default="data/eval/candidates.jsonl")
    e = sub.add_parser("export-csv")
    e.add_argument("--candidates", default="data/eval/candidates.jsonl")
    e.add_argument("--csv", default="data/eval/review.csv")
    i = sub.add_parser("import-csv")
    i.add_argument("--candidates", default="data/eval/candidates.jsonl")
    i.add_argument("--csv", default="data/eval/review.csv")
    i.add_argument("--out", default="data/eval/eval_set.jsonl")
    a = ap.parse_args()
    {"candidates": candidates, "export-csv": export_csv, "import-csv": import_csv}[a.cmd](a)


if __name__ == "__main__":
    main()
