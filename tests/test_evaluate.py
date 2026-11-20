import json
from pathlib import Path

import training.evaluate as evaluation
from training.evaluate import morpheme_tokens, sari, text_metrics


def test_sari_rewards_reference_like_edits_and_metrics_use_gate_keys():
    src = "구비서류를 지참하여 행정복지센터에 방문 접수하여야 합니다."
    ref = "필요한 서류를 가지고 행정복지센터에 가서 신청해야 합니다."
    assert sari(src, ref, ref) > sari(src, src, ref) > 0  # 원문 그대로 베끼면 SARI가 낮다
    m = text_metrics([src, "과태료의 100분의 20을 감경한다."], [ref, "벌금을 20% 줄여 준다."], [ref, ref],
                     ["과태료", "행정복지센터"], {"구비서류": {"alternatives": ["필요한 서류"], "sources": ["NIKL"]}})
    assert m["number_date_amount_match_rate"] == 1.0  # 100분의 20 = 20%
    assert m["preserved_terms_retention_rate"] == 0.5  # 행정복지센터 유지, 과태료 사라짐
    assert m["difficult_term_retention_rate"] == 0.0  # 구비서류가 풀렸음
    assert m["counts"]["difficult_terms_by_source"] == {"NIKL": 1}


def test_morpheme_sari_splits_common_korean_particles():
    assert morpheme_tokens("서류를 내요.") == ["서류", "를", "내요", "."]


def test_evaluate_scores_against_reference_and_records_diagnostics(tmp_path, monkeypatch):
    class Simplifier:
        dummy = False

        def __init__(self, _model_dir):
            pass

        def simplify_detailed(self, sentences):
            return [(s.replace("어려운", "쉬운"), False) for s in sentences]

    monkeypatch.setattr(evaluation, "simplify_timed",
                        lambda _dir, srcs: ([s.replace("어려운", "쉬운") for s in srcs], [False] * len(srcs), [1.0] * len(srcs)))
    monkeypatch.setattr(evaluation, "_is_int8", lambda _path: True)
    monkeypatch.setattr(evaluation, "model_memory_mb", lambda *_args: 12.0)
    monkeypatch.setattr(evaluation, "nikl_dict", lambda *_args: {})
    monkeypatch.setattr(evaluation, "preserve_terms", lambda: [])
    seen = []

    def fake_bert(groups):
        # 진단(원문·교사)은 지연 측정 전에 따로, 모델 출력은 뒤에 따로 부른다
        seen.append(set(groups))
        values = {"output_ref": 0.82, "output_source": 0.91, "source_copy": 0.91, "teacher": 0.76}
        return {k: values[k] for k in groups}

    monkeypatch.setattr(evaluation, "bert_score_groups", fake_bert)
    model_dir = tmp_path / "models" / "v"
    model_dir.mkdir(parents=True)
    for f in ("encoder.onnx", "decoder.onnx"):
        (model_dir / f).write_bytes(b"")
    eval_dir = tmp_path / "data" / "eval"
    eval_dir.mkdir(parents=True)
    eval_path = eval_dir / "eval_set.jsonl"
    rows = [{"id": "e1", "src": "원문 어려운 문장입니다.", "ref": "정답 쉬운 문장입니다."},
            {"id": "e2", "src": "원문 어려운 문장입니다.", "ref": "정답 쉬운 문장입니다."}]
    eval_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    (eval_dir / "candidates.jsonl").write_text("".join(json.dumps({"id": f"e{i}", "teacher": "교사 답입니다."}, ensure_ascii=False) + "\n"
                                                   for i in (1, 2)))

    metrics = evaluation.evaluate("v", eval_path, model_root=tmp_path / "models", data_dir=tmp_path / "data",
                                  out=tmp_path / "report.json")
    assert metrics["bert_score_ref"] == 0.82
    assert metrics["bert_score_source"] == 0.91
    assert metrics["test_set_sha1"]
    assert metrics["diagnostics"]["source_copy"]["bert_score_ref"] == 0.91
    assert metrics["diagnostics"]["teacher"]["bert_score_ref"] == 0.76
    assert metrics["diagnostics"]["teacher"]["count"] == 2
    assert "sari_morpheme" in metrics["diagnostics"]["source_copy"]
    assert seen == [{"source_copy", "teacher"}, {"output_ref", "output_source"}]
    assert json.loads((tmp_path / "report.json").read_text())["test"] == "data/eval/eval_set.jsonl"
    evaluation.evaluate("v", eval_path, model_root=tmp_path / "models", data_dir=tmp_path / "data", out=tmp_path / "r2.json")
    assert seen[2:] == [{"output_ref", "output_source"}]  # 같은 평가셋이면 진단은 캐시


def test_bert_score_groups_unpacks_candidate_and_target_lists(monkeypatch):
    import sys, types
    f1 = types.SimpleNamespace(tolist=lambda: [0.5, 0.7, 0.9])  # torch 없이: score()[2].tolist()만 흉내
    fake = types.SimpleNamespace(score=lambda c, r, **k: (None, None, f1))
    monkeypatch.setitem(sys.modules, "bert_score", fake)
    from training.evaluate import bert_score_groups
    assert bert_score_groups({"model": (["a", "b"], ["x", "y"]), "teacher": (["c"], ["z"]), "empty": ([], [])}) == {
        "model": 0.6, "teacher": 0.9}


def test_sari_multi_reference_matches_single_and_rewards_any_reference():
    from training.evaluate import references, sari, sari_morpheme
    src, out = "원문의 어려운 낱말을 씁니다.", "원문의 쉬운 말을 씁니다."
    assert sari(src, out, "원문의 쉬운 말을 씁니다.") == sari(src, out, ["원문의 쉬운 말을 씁니다."])
    other = "처음 글의 쉬운 말을 씁니다."
    assert sari(src, out, [other, "원문의 쉬운 말을 씁니다."]) > sari(src, out, [other])
    assert sari_morpheme(src, out, [other, out]) > sari_morpheme(src, out, [other])
    assert references({"src": "a", "references": ["b", "c"]}) == ["b", "c"]
    assert references({"src": "a", "ref": "b"}) == ["b"] and references({"src": "a", "tgt": "t"}) == ["t"]


def test_bert_score_groups_takes_best_reference(monkeypatch):
    import sys, types
    seen = {}

    def fake_score(c, r, **k):
        seen["pairs"] = list(zip(c, r))
        return None, None, types.SimpleNamespace(tolist=lambda: [0.2, 0.9, 0.5])
    monkeypatch.setitem(sys.modules, "bert_score", types.SimpleNamespace(score=fake_score))
    from training.evaluate import bert_score_groups
    got = bert_score_groups({"model": (["o1", "o2"], [["r1", "r2"], "r3"])})
    assert seen["pairs"] == [("o1", "r1"), ("o1", "r2"), ("o2", "r3")]
    assert got == {"model": round((0.9 + 0.5) / 2, 4)}


def test_references_rejects_bad_types_and_bert_groups_rejects_length_mismatch(monkeypatch):
    import sys, types
    import pytest
    from training.evaluate import bert_score_groups, references
    with pytest.raises(TypeError):
        references({"id": "e1", "src": "a", "references": "글자로 쪼개지면 안 됨"})
    with pytest.raises(ValueError):
        references({"id": "e1", "src": "a", "references": []})
    with pytest.raises(ValueError):
        references({"id": "e1", "src": "a", "references": ["좋음", ""]})
    with pytest.raises(ValueError):
        references({"id": "e1", "src": "a"})
    monkeypatch.setitem(sys.modules, "bert_score", types.SimpleNamespace(score=lambda c, r, **k: (None, None, None)))
    with pytest.raises(ValueError):
        bert_score_groups({"model": (["o1", "o2"], ["r1"])})


def test_reference_diagnostics_cached_per_eval_set_sha(tmp_path, monkeypatch):
    import hashlib
    from training import evaluate as ev
    path = tmp_path / "eval_set.jsonl"
    rows = [{"id": "e1", "src": "어려운 원문입니다.", "references": ["쉬운 말입니다.", "쉬운 글입니다."], "teacher": "쉬운 말입니다."}]
    path.write_text(json.dumps(rows[0], ensure_ascii=False) + "\n", encoding="utf-8")
    sha = hashlib.sha1(path.read_bytes()).hexdigest()
    calls = []
    monkeypatch.setattr(ev, "bert_score_groups", lambda groups: calls.append(1) or {k: 0.5 for k in groups})
    first = ev.reference_diagnostics(rows, path, sha)
    second = ev.reference_diagnostics(rows, path, sha)
    assert first == second and len(calls) == 1
    assert first["source_copy"]["bert_score_ref"] == 0.5 and first["teacher"]["count"] == 1
    assert ev.reference_diagnostics(rows, path, "0" * 40) and len(calls) == 2  # 다른 지문이면 다시 계산


def test_display_path_is_relative_to_data_dir(tmp_path):
    from training.evaluate import _display_path
    data = tmp_path / "data"
    (data / "eval").mkdir(parents=True)
    assert _display_path(data / "eval" / "eval_set.jsonl", data) == "data/eval/eval_set.jsonl"
    assert _display_path(tmp_path / "other.jsonl", data) == "other.jsonl"


def test_evaluate_checks_int8_before_any_work(tmp_path, monkeypatch):
    import pytest
    called = []
    monkeypatch.setattr(evaluation, "simplify_timed", lambda *a: called.append("timed"))
    monkeypatch.setattr(evaluation, "reference_diagnostics", lambda *a, **k: called.append("diag"))
    monkeypatch.setattr(evaluation, "_is_int8", lambda _path: False)
    model_dir = tmp_path / "models" / "v"
    model_dir.mkdir(parents=True)
    for f in ("encoder.onnx", "decoder.onnx"):
        (model_dir / f).write_bytes(b"")
    path = tmp_path / "eval.jsonl"
    path.write_text(json.dumps({"src": "a", "ref": "b"}) + "\n")
    with pytest.raises(ValueError, match="INT8"):
        evaluation.evaluate("v", path, model_root=tmp_path / "models", data_dir=tmp_path)
    assert called == []


def test_diagnostics_cache_key_includes_candidates_and_write_failure_only_warns(tmp_path, monkeypatch):
    import hashlib
    import warnings
    path = tmp_path / "eval_set.jsonl"
    rows = [{"id": "e1", "src": "어려운 원문입니다.", "references": ["쉬운 말입니다.", "쉬운 글입니다."]}]
    path.write_text(json.dumps(rows[0], ensure_ascii=False) + "\n", encoding="utf-8")
    sha = hashlib.sha1(path.read_bytes()).hexdigest()
    (tmp_path / "candidates.jsonl").write_text(json.dumps({"id": "e1", "teacher": "교사 1"}, ensure_ascii=False) + "\n", encoding="utf-8")
    calls = []
    monkeypatch.setattr(evaluation, "bert_score_groups", lambda groups: calls.append(1) or {k: 0.5 for k in groups})
    evaluation.reference_diagnostics(rows, path, sha)
    evaluation.reference_diagnostics(rows, path, sha)
    assert len(calls) == 1
    (tmp_path / "candidates.jsonl").write_text(json.dumps({"id": "e1", "teacher": "교사 2"}, ensure_ascii=False) + "\n", encoding="utf-8")
    evaluation.reference_diagnostics(rows, path, sha)
    assert len(calls) == 2  # candidates가 바뀌면 다시 계산
    monkeypatch.setattr(evaluation.os, "replace", lambda *a: (_ for _ in ()).throw(OSError("disk full")))
    (tmp_path / "candidates.jsonl").write_text("", encoding="utf-8")
    with warnings.catch_warnings(record=True) as got:
        warnings.simplefilter("always")
        assert evaluation.reference_diagnostics(rows, path, sha)["source_copy"]["count"] == 1
    assert any("캐시를 쓰지 못함" in str(w.message) for w in got)
