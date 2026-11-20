"""models/<version>/ 를 test 분할로 평가해 metadata.json metrics 에 게이트 키(gate/thresholds.json)로 기록.

`python -m training.evaluate --version v1 [--test data/v1/test.jsonl]`
"""
import argparse, collections, hashlib, json, re, statistics, subprocess, sys, time
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


PARTICLES = tuple(sorted(("으로부터", "에게서", "에서는", "까지는", "으로", "에서", "에게", "부터", "까지",
                          "처럼", "보다", "만큼", "이랑", "하고", "은", "는", "이", "가", "을", "를", "에",
                          "의", "와", "과", "도", "만", "로"), key=len, reverse=True))


def morpheme_tokens(text):
    """설치된 형태소 분석기가 없어 공백 단위에서 마지막 조사만 나누는 근사 토크나이저."""
    out = []
    for token in TOKEN.findall(text):
        if re.fullmatch(r"[가-힣]+", token):
            particle = next((p for p in PARTICLES if token.endswith(p) and len(token) - len(p) >= 2), None)
            if particle:
                out.extend((token[:-len(particle)], particle))
                continue
        out.append(token)
    return out


def sari_morpheme(src, out, ref):
    s, c, r = (morpheme_tokens(x) for x in (src, out, ref))
    parts = [_sari_ngram(_ngrams(s, n), _ngrams(c, n), _ngrams(r, n)) for n in range(1, 5)]
    return sum(sum(p[i] for p in parts) / 4 for i in range(3)) / 3


def text_metrics(srcs, outs, refs, preserve, nikl):
    keep_terms = [(t, o) for s, o in zip(srcs, outs) for t in preserve if found(t, s)]
    hard = [(t, o) for s, o in zip(srcs, outs) for t in nikl if found(t, s)]
    by_source = collections.Counter(source for s in srcs for term, entry in nikl.items() if found(term, s)
                                    for source in entry["sources"])
    return {
        "number_date_amount_match_rate": round(sum(numbers(s) == numbers(o) for s, o in zip(srcs, outs)) / len(srcs), 4),
        "preserved_terms_retention_rate": round(sum(t in o for t, o in keep_terms) / len(keep_terms), 4) if keep_terms else 1.0,
        "difficult_term_retention_rate": round(sum(found(t, o) for t, o in hard) / len(hard), 4) if hard else 0.0,
        "sentence_length_reduction_rate": round(1 - sum(map(len, outs)) / sum(map(len, srcs)), 4),
        "sari": round(statistics.mean(sari(s, o, r) for s, o, r in zip(srcs, outs, refs)), 4),
        "sari_morpheme": round(statistics.mean(sari_morpheme(s, o, r) for s, o, r in zip(srcs, outs, refs)), 4),
        "counts": {"sentences": len(srcs), "preserved_terms": len(keep_terms), "difficult_terms": len(hard),
                   "difficult_terms_by_source": dict(sorted(by_source.items()))},
    }


def bert_score_groups(groups):
    from bert_score import score  # bert-base-multilingual-cased (lang="ko" 기본값)

    names, cands, refs, spans = [], [], [], {}
    for name, candidates, targets in groups.items():
        if candidates:
            start = len(cands)
            names.append(name)
            spans[name] = (start, start + len(candidates))
            cands.extend(candidates)
            refs.extend(targets)
    values = score(cands, refs, lang="ko", verbose=False)[2].tolist()
    return {name: round(statistics.mean(values[start:end]), 4) for name, (start, end) in spans.items()}


def _reference_diagnostics(rows, test_path):
    srcs, refs = [r["src"] for r in rows], [r.get("ref", r.get("tgt", "")) for r in rows]
    candidates_path = Path(test_path).with_name("candidates.jsonl")
    candidates = {}
    if candidates_path.is_file():
        candidates = {r["id"]: r.get("teacher", "") for r in
                      (json.loads(line) for line in candidates_path.read_text(encoding="utf-8").splitlines() if line)}
    teacher_rows = [(r["src"], r.get("teacher") or candidates.get(r.get("id"), ""), r.get("ref", r.get("tgt", "")))
                    for r in rows]
    teacher_rows = [(s, t, ref) for s, t, ref in teacher_rows if t]

    source = {"count": len(srcs),
              "sari": round(statistics.mean(sari(s, s, ref) for s, ref in zip(srcs, refs)), 4),
              "sari_morpheme": round(statistics.mean(sari_morpheme(s, s, ref) for s, ref in zip(srcs, refs)), 4)}
    teachers = [t for _, t, _ in teacher_rows]
    teacher_refs = [ref for _, _, ref in teacher_rows]
    teacher = {"count": len(teacher_rows)}
    if teacher_rows:
        teacher.update({"sari": round(statistics.mean(sari(s, t, ref) for s, t, ref in teacher_rows), 4),
                        "sari_morpheme": round(statistics.mean(sari_morpheme(s, t, ref) for s, t, ref in teacher_rows), 4)})
    groups = {"source_copy": (srcs, refs)}
    if teacher_rows:
        groups["teacher"] = (teachers, teacher_refs)
    return {"source_copy": source, "teacher": teacher}, groups


MEMORY_PROBE = """import resource, sys, numpy, onnxruntime, tokenizers
from simple_word.model import Simplifier
before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
Simplifier(sys.argv[1]).simplify(sys.argv[2:])
print((resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - before) / 2**20)  # macOS ru_maxrss 단위는 바이트
"""


def model_memory_mb(model_dir, sample):
    """새 프로세스에서 라이브러리 import 뒤 모델 불러오기+추론으로 늘어난 최대 RSS(MB)."""
    runs = [subprocess.run([sys.executable, "-c", MEMORY_PROBE, str(model_dir), *sample], capture_output=True, text=True, check=True)
            for _ in range(3)]  # 한 번 재면 ±30MB 흔들려서 3번의 중앙값
    return round(statistics.median(float(r.stdout.strip().splitlines()[-1]) for r in runs), 1)


def _graph(path):
    import onnx

    return onnx.load(str(path), load_external_data=False).graph


def _is_int8(path):
    """quantize_dynamic 결과 그래프에는 DynamicQuantizeLinear / MatMulInteger 노드가 있다."""
    g = _graph(path)
    return any(n.op_type in ("DynamicQuantizeLinear", "MatMulInteger", "DynamicQuantizeMatMul") for n in g.node)


def evaluate(version, test_path, model_root="models", data_dir="data", with_bert=True, out=None):
    """out이 없으면 metadata.json metrics(게이트가 읽는 값)에 쓴다. out을 주면 그 JSON 파일에만 쓰고 metadata는 건드리지 않는다
    (예: 사람·Claude 검수 평가셋 지표). SARI와 bert_score_ref는 tgt/ref 기준이고, bert_score_source는 진단용이다."""
    from simple_word.model import Simplifier

    model_dir = Path(model_root) / version
    test_path = Path(test_path)
    eval_set_sha1 = hashlib.sha1(test_path.read_bytes()).hexdigest()
    rows = [json.loads(l) for l in test_path.read_text(encoding="utf-8").splitlines() if l]
    if not rows:
        raise ValueError(f"{test_path}: evaluation set is empty")
    srcs, refs = [r["src"] for r in rows], [r["tgt"] if "tgt" in r else r["ref"] for r in rows]
    simp, outs, ms = Simplifier(str(model_dir)), [], []
    if simp.dummy or not all(_is_int8(model_dir / f) for f in ("encoder.onnx", "decoder.onnx")):
        raise ValueError(f"{model_dir}: INT8 ONNX 모델이 아니다. 게이트 지표는 서빙과 같은 INT8 ONNX로만 계산한다")
    fallbacks = []
    for s in srcs:
        t = time.perf_counter()
        [(o, fb)] = simp.simplify_detailed([s])  # 서빙과 같은 경로(숫자 안전장치 포함)
        ms.append((time.perf_counter() - t) * 1000)
        outs.append(o)
        fallbacks.append(fb)
    m = text_metrics(srcs, outs, refs, preserve_terms(), nikl_dict(data_dir))
    bert_groups = {"output_ref": (outs, refs), "output_source": (outs, srcs)}
    diagnostics = None
    if all("ref" in row for row in rows):
        diagnostics, reference_groups = _reference_diagnostics(rows, test_path)
        bert_groups.update({f"diagnostics_{name}": pair for name, pair in reference_groups.items()})
    if with_bert:
        bert_scores = bert_score_groups(bert_groups)
        m["bert_score_ref"] = bert_scores["output_ref"]
        m["bert_score_source"] = bert_scores["output_source"]
        if diagnostics is not None:
            diagnostics["source_copy"]["bert_score_ref"] = bert_scores["diagnostics_source_copy"]
            if "diagnostics_teacher" in bert_scores:
                diagnostics["teacher"]["bert_score_ref"] = bert_scores["diagnostics_teacher"]
    m["fallback_rate"] = round(sum(fallbacks) / len(fallbacks), 4)  # 숫자 안전장치로 원문을 돌려준 비율
    m["cpu_p95_ms_per_sentence"] = round(statistics.quantiles(ms, n=20)[18], 1)
    m["model_memory_mb"] = model_memory_mb(model_dir, srcs[:20])
    m["eval_model"] = "onnx_int8_cpu"  # 게이트 지표는 서빙과 같은 INT8 ONNX(onnxruntime CPU, 스레드 1) 출력에서 계산
    m["test_set_sha1"] = eval_set_sha1
    if diagnostics is not None:
        m["diagnostics"] = diagnostics
    lines = "".join(json.dumps({"src": s, "out": o, "ref": r, "fallback": f}, ensure_ascii=False) + "\n"
                    for s, o, r, f in zip(srcs, outs, refs, fallbacks))
    if out:
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"version": version, "test": str(test_path), "metrics": m}, ensure_ascii=False, indent=1), encoding="utf-8")
        out.with_suffix(".outputs.jsonl").write_text(lines, encoding="utf-8")
        return m
    meta_path = model_dir / "metadata.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["metrics"].pop("bert_score", None)
    meta["metrics"].update(m)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    (model_dir / "test_outputs.jsonl").write_text(lines, encoding="utf-8")
    return m


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--test")
    ap.add_argument("--data", default="data")
    ap.add_argument("--no-bert", action="store_true")
    ap.add_argument("--models", default="models")
    ap.add_argument("--out", help="metadata.json 대신 이 JSON에 지표를 쓴다(평가셋 등)")
    a = ap.parse_args()
    print(json.dumps(evaluate(a.version, a.test or f"{a.data}/{a.version}/test.jsonl", model_root=a.models, data_dir=a.data,
                              with_bert=not a.no_bert, out=a.out), ensure_ascii=False))
