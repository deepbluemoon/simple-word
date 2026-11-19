"""models/<version>/ 를 test 분할로 평가해 metadata.json metrics 에 게이트 키(gate/thresholds.json)로 기록.

`python -m training.evaluate --version v1 [--test data/v1/test.jsonl]`
"""
import argparse, collections, json, re, statistics, subprocess, sys, time
from pathlib import Path

from training.checks import numbers
from training.terms import found, nikl_dict, preserve_terms

TOKEN = re.compile(r"\w+|[^\w\s]")


def _ngrams(tokens, n):
    return [" ".join(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]


def _sari_ngram(s, c, r):
    """Xu et al. 2016 SARI 한 n-gram 차수, 참조 1개. keep F1, delete 정밀도, add F1."""
    sc, cc, rc = collections.Counter(s), collections.Counter(c), collections.Counter(r)
    keep, keep_good, keep_all = sc & cc, sc & cc & rc, sc & rc
    kp = sum(keep_good[g] / keep[g] for g in keep) / len(keep) if keep else 1
    kr = sum(keep_good.values()) / sum(keep_all.values()) if keep_all else 1  # easse 구현과 같음
    delete = sc - cc
    del_good = delete - rc
    dp = sum(del_good[g] / delete[g] for g in delete) / len(delete) if delete else 1
    add, add_all = set(cc) - set(sc), set(rc) - set(sc)
    add_good = add & set(rc)
    ap = len(add_good) / len(add) if add else 1
    ar = len(add_good) / len(add_all) if add_all else 1
    f1 = lambda p, q: 2 * p * q / (p + q) if p + q else 0
    return f1(kp, kr), dp, f1(ap, ar)


def sari(src, out, ref):
    s, c, r = (TOKEN.findall(x) for x in (src, out, ref))
    parts = [_sari_ngram(_ngrams(s, n), _ngrams(c, n), _ngrams(r, n)) for n in range(1, 5)]
    return sum(sum(p[i] for p in parts) / 4 for i in range(3)) / 3


def text_metrics(srcs, outs, refs, preserve, nikl):
    keep_terms = [(t, o) for s, o in zip(srcs, outs) for t in preserve if found(t, s)]
    hard = [(t, o) for s, o in zip(srcs, outs) for t in nikl if len(t) >= 2 and found(t, s)]
    return {
        "number_date_amount_match_rate": round(sum(numbers(s) == numbers(o) for s, o in zip(srcs, outs)) / len(srcs), 4),
        "preserved_terms_retention_rate": round(sum(t in o for t, o in keep_terms) / len(keep_terms), 4) if keep_terms else 1.0,
        "difficult_term_retention_rate": round(sum(found(t, o) for t, o in hard) / len(hard), 4) if hard else 0.0,
        "sentence_length_reduction_rate": round(1 - sum(map(len, outs)) / sum(map(len, srcs)), 4),
        "sari": round(statistics.mean(sari(s, o, r) for s, o, r in zip(srcs, outs, refs)), 4),
        "counts": {"sentences": len(srcs), "preserved_terms": len(keep_terms), "difficult_terms": len(hard)},
    }


def bert_score_f1(cands, refs):
    from bert_score import score  # bert-base-multilingual-cased (lang="ko" 기본값)

    return round(score(cands, refs, lang="ko", verbose=False)[2].mean().item(), 4)


MEMORY_PROBE = """import resource, sys, numpy, onnxruntime, tokenizers
from simple_word.model import Simplifier
before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
Simplifier(sys.argv[1]).simplify(sys.argv[2:])
print((resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - before) / 2**20)  # macOS ru_maxrss 단위는 바이트
"""


def model_memory_mb(model_dir, sample):
    """새 프로세스에서 라이브러리 import 뒤 모델 불러오기+추론으로 늘어난 최대 RSS."""
    out = subprocess.run([sys.executable, "-c", MEMORY_PROBE, str(model_dir), *sample], capture_output=True, text=True, check=True)
    return round(float(out.stdout.strip().splitlines()[-1]), 1)


def evaluate(version, test_path, model_root="models", data_dir="data", with_bert=True):
    from simple_word.model import Simplifier

    model_dir = Path(model_root) / version
    rows = [json.loads(l) for l in Path(test_path).open(encoding="utf-8")]
    srcs, refs = [r["src"] for r in rows], [r["tgt"] for r in rows]
    simp, outs, ms = Simplifier(str(model_dir)), [], []
    for s in srcs:
        t = time.perf_counter()
        outs += simp.simplify([s])
        ms.append((time.perf_counter() - t) * 1000)
    m = text_metrics(srcs, outs, refs, preserve_terms(), nikl_dict(data_dir))
    if with_bert:
        m["bert_score"] = bert_score_f1(outs, srcs)  # 원문 대비 의미 유사도
    m["cpu_p95_ms_per_sentence"] = round(statistics.quantiles(ms, n=20)[18], 1)
    m["model_memory_mb"] = model_memory_mb(model_dir, srcs[:20])
    meta_path = model_dir / "metadata.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["metrics"].update(m)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    (model_dir / "test_outputs.jsonl").write_text("".join(json.dumps({"src": s, "out": o, "ref": r}, ensure_ascii=False) + "\n"
                                                          for s, o, r in zip(srcs, outs, refs)), encoding="utf-8")
    return m


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--test")
    ap.add_argument("--data", default="data")
    ap.add_argument("--no-bert", action="store_true")
    a = ap.parse_args()
    print(json.dumps(evaluate(a.version, a.test or f"{a.data}/{a.version}/test.jsonl", data_dir=a.data, with_bert=not a.no_bert), ensure_ascii=False))
