"""짝 판정 방법(NLI, NLI+교사 LLM, 내용어 정렬)의 정확도를 재는 정답 표본(docs/NLI_FILTER.md "판정 보정").

    python -m training.judge_gold sample --out data/judge_gold.todo.jsonl   # 100짝 뽑기(라벨 칸 비움)
    python -m training.judge_gold score  --gold data/judge_gold.jsonl       # 정밀도·재현율·F1 표

표본: NLI 표시 짝 50 + 표시 안 된 짝 50. 부처 × 길이(3구간) × 게시 시기(앞·뒤 절반) 층마다 돌아가며 뽑는다(seed 0).
라벨: ok / contradiction(모순) / omission(누락) / other(기타 오류). ok가 아닌 것을 "문제 짝"으로 본다.
"""
import argparse
import json
import random
import re
from collections import defaultdict
from pathlib import Path

SEED = 0
LABELS = ("ok", "contradiction", "omission", "other")


def _strata(rows, published):
    lens = sorted(len(r["src"]) for r in rows)
    cut = (lens[len(lens) // 3], lens[2 * len(lens) // 3])
    dates = sorted(published.get(r["doc_id"], "") for r in rows)
    mid = dates[len(dates) // 2]
    key = lambda r: (r["doc_id"].split("-")[0], sum(len(r["src"]) > c for c in cut), published.get(r["doc_id"], "") > mid)
    by = defaultdict(list)
    for r in rows:
        by[key(r)].append(r)
    return by


def stratified(rows, n, published, seed=SEED):
    rng = random.Random(seed)
    by = _strata(rows, published)
    for k in by:
        rng.shuffle(by[k])
    keys = sorted(by)
    rng.shuffle(keys)
    out = []
    while len(out) < n and any(by.values()):
        for k in keys:
            if by[k] and len(out) < n:
                out.append(by[k].pop())
    return out


def sample(data_dir="data", n_each=50):
    data = Path(data_dir)
    pairs = [p for p in map(json.loads, open(data / "pairs.jsonl", encoding="utf-8")) if p.get("passed") and p.get("tgt")]
    nli = {(r["doc_id"], r["idx"]): r for r in map(json.loads, open(data / "nli.jsonl", encoding="utf-8"))}
    published = {d["id"]: d["published_at"] for d in map(json.loads, open(data / "docs.jsonl", encoding="utf-8"))}
    flagged = [p for p in pairs if nli.get((p["doc_id"], p["idx"]), {}).get("flag")]
    clean = [p for p in pairs if (p["doc_id"], p["idx"]) in nli and not nli[(p["doc_id"], p["idx"])].get("flag")]
    picked = [(p, True) for p in stratified(flagged, n_each, published)] + [(p, False) for p in stratified(clean, n_each, published, SEED + 1)]
    return [{"doc_id": p["doc_id"], "idx": p["idx"], "nli_flagged": f, "src": p["src"], "tgt": p["tgt"],
             "published_at": published.get(p["doc_id"]), "label": None, "why": None} for p, f in picked]


# ---------- C: 내용어 정렬 ----------
PARTICLES = ("으로부터", "에게서", "에서는", "으로는", "에서", "에게", "으로", "부터", "까지", "처럼", "보다", "만큼",
             "하고", "이며", "이고", "에는", "와", "과", "은", "는", "이", "가", "을", "를", "에", "의", "도", "만", "로")
STOP = {"이번", "또한", "아울러", "등을", "통해", "위해", "대한", "관련", "이날", "그리고", "한편", "특히", "있는", "하는",
        "했다", "밝혔다", "한다", "있다", "된다", "예정이다", "계획이다", "것이다"}


def content_words(text):
    """한글 2글자 이상 어절에서 끝 조사를 떼고, 숫자·영문 낱말은 그대로 둔 내용어 목록(근사)."""
    out = []
    for w in re.findall(r"[가-힣]+|[A-Za-z]{2,}|\d[\d,.]*", text):
        if re.fullmatch(r"[가-힣]+", w):
            w = next((w[:-len(p)] for p in PARTICLES if w.endswith(p) and len(w) - len(p) >= 2), w)
            if len(w) < 2 or w in STOP:
                continue
        out.append(w)
    return out


def aligned(word, tgt, alternatives):
    if word in tgt:
        return True
    stem = word[:2] if re.fullmatch(r"[가-힣]{3,}", word) else None  # '지원한다'·'지원을' 같은 활용·복합어
    if stem and stem in tgt:
        return True
    return any(a in tgt for a in alternatives.get(word, ()))


def coverage(src, tgt, alternatives):
    words = content_words(src)
    return sum(aligned(w, tgt, alternatives) for w in words) / len(words) if words else 1.0


def score(gold_path, data_dir="data", c_threshold=0.5):
    from training.terms import nikl_dict
    nikl = {t: e["alternatives"] for t, e in nikl_dict(data_dir).items()}
    nli = {(r["doc_id"], r["idx"]): r for r in map(json.loads, open(Path(data_dir) / "nli.jsonl", encoding="utf-8"))}
    gold = [json.loads(l) for l in open(gold_path, encoding="utf-8")]
    methods = {
        "NLI 단독": lambda g, r: bool(r.get("flag")),
        "NLI+gemma 2단계": lambda g, r: bool(r.get("exclude") if "exclude" in r else r.get("flag")),
        f"C 내용어 정렬(<{c_threshold})": lambda g, r: coverage(g["src"], g["tgt"], nikl) < c_threshold,
    }
    rows = {}
    for name, pred in methods.items():
        for part in ("all", "flagged", "clean"):
            sub = [g for g in gold if part == "all" or g["nli_flagged"] == (part == "flagged")]
            tp = sum(pred(g, nli[(g["doc_id"], g["idx"])]) and g["label"] != "ok" for g in sub)
            fp = sum(pred(g, nli[(g["doc_id"], g["idx"])]) and g["label"] == "ok" for g in sub)
            fn = sum(not pred(g, nli[(g["doc_id"], g["idx"])]) and g["label"] != "ok" for g in sub)
            p = tp / (tp + fp) if tp + fp else None
            rc = tp / (tp + fn) if tp + fn else None
            f1 = 2 * p * rc / (p + rc) if p and rc else None
            rows[(name, part)] = {"tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": rc, "f1": f1}
    labels = {part: {l: sum(g["label"] == l for g in gold if g["nli_flagged"] == (part == "flagged")) for l in LABELS}
              for part in ("flagged", "clean")}
    cov = sorted((round(coverage(g["src"], g["tgt"], nikl), 3), g["label"] != "ok") for g in gold)
    return rows, labels, cov


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["sample", "score"])
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="data/judge_gold.todo.jsonl")
    ap.add_argument("--gold", default="data/judge_gold.jsonl")
    ap.add_argument("--c-threshold", type=float, default=0.5)
    a = ap.parse_args()
    if a.cmd == "sample":
        rows = sample(a.data)
        Path(a.out).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        print(len(rows), a.out)
    else:
        rows, labels, cov = score(a.gold, a.data, a.c_threshold)
        print(json.dumps(labels, ensure_ascii=False))
        for (name, part), m in rows.items():
            print(name, part, m)
        print("coverage(label!=ok)", cov)
