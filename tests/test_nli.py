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
