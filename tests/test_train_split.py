import json

from training.train import make_splits


def test_split_keeps_each_document_in_one_split(tmp_path):
    pairs = [{"doc_id": f"d{i // 3}", "src": f"s{i}", "tgt": f"t{i}", "passed": i % 7 != 0} for i in range(300)]
    (tmp_path / "pairs.jsonl").write_text("".join(json.dumps(p) + "\n" for p in pairs))
    a = make_splits([tmp_path / "pairs.jsonl"], tmp_path / "v1")
    b = make_splits([tmp_path / "pairs.jsonl"], tmp_path / "v2")
    assert a == b  # 결정적
    owner = {}
    for name, rows in a.items():
        for r in rows:
            assert owner.setdefault(r["doc_id"], name) == name
    assert sum(map(len, a.values())) == sum(p["passed"] for p in pairs) and all(a.values())
