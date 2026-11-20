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

    monkeypatch.setattr("simple_word.model.Simplifier", Simplifier)
    monkeypatch.setattr(evaluation, "_is_int8", lambda _path: True)
    monkeypatch.setattr(evaluation, "model_memory_mb", lambda *_args: 12.0)
    monkeypatch.setattr(evaluation, "nikl_dict", lambda *_args: {})
    monkeypatch.setattr(evaluation, "preserve_terms", lambda: [])
    def fake_bert(groups):
        assert set(groups) == {"output_ref", "output_source", "diagnostics_source_copy", "diagnostics_teacher"}
        return {"output_ref": 0.82, "output_source": 0.91, "diagnostics_source_copy": 0.91, "diagnostics_teacher": 0.76}

    monkeypatch.setattr(evaluation, "bert_score_groups", fake_bert)
    model_dir = tmp_path / "models" / "v"
    model_dir.mkdir(parents=True)
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


def test_bert_score_groups_unpacks_candidate_and_target_lists(monkeypatch):
    import sys, types
    import torch
    fake = types.SimpleNamespace(score=lambda c, r, **k: (None, None, torch.tensor([0.5, 0.7, 0.9])))
    monkeypatch.setitem(sys.modules, "bert_score", fake)
    from training.evaluate import bert_score_groups
    assert bert_score_groups({"model": (["a", "b"], ["x", "y"]), "teacher": (["c"], ["z"]), "empty": ([], [])}) == {
        "model": 0.6, "teacher": 0.9}
