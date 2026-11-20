import json

from training.nli import flag, load_flags
from training.train import make_splits


def _r(fc, bc, fe=0.9, be=0.9):
    return {"fwd": {"entailment": fe, "contradiction": fc}, "bwd": {"entailment": be, "contradiction": bc}}


def test_flag_rules():
    assert flag(_r(0.01, 0.02)) is None
    assert flag(_r(0.95, 0.0)) == "contradiction" and flag(_r(0.0, 0.95)) == "contradiction"
    assert flag(_r(0.0, 0.0, fe=0.3, be=0.01)) == "omission"
    assert flag(_r(0.0, 0.0, fe=0.9, be=0.01)) is None  # 원문이 쉬운 말을 뒷받침하면 세부를 줄인 것으로 본다


def test_make_splits_excludes_flagged_only_from_train(tmp_path):
    pairs = tmp_path / "pairs.jsonl"
    rows = [{"doc_id": f"d{i}", "idx": 0, "src": f"원문 {i}", "tgt": f"쉬운 말 {i}", "passed": True} for i in range(40)]
    pairs.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    nli = tmp_path / "nli.jsonl"
    nli.write_text("".join(json.dumps({"doc_id": r["doc_id"], "idx": 0, "flag": "contradiction"}) + "\n" for r in rows), encoding="utf-8")
    base = make_splits([pairs], tmp_path / "a")
    cut = make_splits([pairs], tmp_path / "b", exclude=load_flags(nli))
    assert base["train"] and not cut["train"]
    assert cut["valid"] == base["valid"] and cut["test"] == base["test"]


def test_llm_parse_exclude_and_load_flags_prefers_exclude(tmp_path):
    from training.nli_llm import exclude, parse
    assert parse('{"differences": ["a → b: 다름"], "verdict": "omission"}') == {"verdict": "omission", "reason": "a → b: 다름"}
    assert parse("앞말 {\"verdict\": \"SAME\"} 뒷말")["verdict"] == "same"
    assert parse("엉망")["verdict"] == "unknown" and not exclude({"verdict": "unknown"})
    assert exclude({"verdict": "contradiction"}) and not exclude({"verdict": "same"})
    p = tmp_path / "nli.jsonl"
    rows = [{"doc_id": "a", "idx": 0, "flag": "omission", "exclude": False},
            {"doc_id": "b", "idx": 0, "flag": "contradiction", "exclude": True},
            {"doc_id": "c", "idx": 0, "flag": "omission"}]
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    assert load_flags(p) == {("b", 0), ("c", 0)}
