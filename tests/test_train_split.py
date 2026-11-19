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


def test_train_refuses_empty_data_and_split_leaks(tmp_path):
    import pytest

    from training.train import leakage, stop_epoch, time_split_of, train

    (tmp_path / "p.jsonl").write_text(json.dumps({"doc_id": "d", "src": "a", "tgt": "b", "passed": False}) + "\n")
    with pytest.raises(ValueError, match="비었다"):  # torch 를 불러오기 전에 멈춤
        train("v", [tmp_path / "p.jsonl"], data_root=tmp_path, model_root=tmp_path)
    rows = [{"doc_id": f"d{i}", "src": f"문장{i}", "tgt": "x"} for i in range(10)]
    owner = time_split_of(rows, {f"d{i}": f"2026-01-{10 + i}" for i in range(10)})
    assert [owner[f"d{i}"] for i in range(10)] == ["train"] * 8 + ["valid", "test"]  # 가장 새 글이 test
    splits = {"train": rows[:8], "valid": [{"doc_id": "d9", "src": "문장 1!", "tgt": "x"}], "test": []}
    assert leakage(splits, ["문장3"]) == {"doc_overlap": 0, "src_exact_overlap": 0, "src_near_overlap": 1, "parity_overlap": 0, "eval_set_overlap": 1}
    assert stop_epoch([2.0, 1.9, 1.95, 1.94]) == (True, 2) and stop_epoch([2.0, 1.9, 1.95]) == (False, 2)
