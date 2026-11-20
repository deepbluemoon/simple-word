import csv, json
from types import SimpleNamespace

import pytest

from training.eval_set import CSV_COLS, export_csv, import_csv, pool, sample, stratum, features


def test_stratum_priority_and_features():
    f = features("「국민건강보험법」에 따라 2026년 3월부터 지원한다", nikl=("지원",), keep=("국민건강보험법",))
    assert stratum(f) == "preserve" and f["numbers"] == ["2026", "3"]
    assert stratum(features("x" * 100, (), ())) == "long" and stratum(features("짧은 말", (), ())) == "general"


def test_pool_excludes_training_and_near_duplicates(tmp_path):
    sp = tmp_path / "v"
    sp.mkdir()
    (sp / "train.jsonl").write_text(json.dumps({"doc_id": "d1", "src": "학습 문장", "tgt": "t"}) + "\n")
    (sp / "valid.jsonl").write_text("")
    (sp / "test.jsonl").write_text(json.dumps({"doc_id": "d2", "src": "시험 문장", "tgt": "t"}) + "\n")
    pairs = [{"doc_id": "d1", "idx": i, "src": s, "tgt": "t", "passed": False}
             for i, s in enumerate(["학습 문장!", "시험  문장", "새 문장", "새 문장.", "다른 문장"])]
    (tmp_path / "p.jsonl").write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in pairs))
    rows = pool(tmp_path / "p.jsonl", sp, (), ())
    assert [r["src"] for r in rows] == ["새 문장", "다른 문장"] and rows[0]["doc_split"] == "train"
    picked = sample(rows, [("numbers", 1), ("general", 1)])  # numbers 가 모자라면 general 로 채운다
    assert len(picked) == 2 and sample(rows, [("general", 2)]) == sample(rows, [("general", 2)])


def test_csv_round_trip(tmp_path):
    cand = [{"id": "e001", "doc_id": "d", "stratum": "general", "src": "원문1", "teacher": "교사1", "teacher_reject": "length",
             "model_out": "원문1", "fallback": True},
            {"id": "e002", "doc_id": "d", "stratum": "numbers", "src": "원문2", "teacher": "교사2", "teacher_reject": None,
             "model_out": "모델2", "fallback": False},
            {"id": "e003", "doc_id": "d", "stratum": "long", "src": "원문3", "teacher": "교사3", "teacher_reject": None,
             "model_out": "모델3", "fallback": False}]
    c, v, o = tmp_path / "c.jsonl", tmp_path / "r.csv", tmp_path / "e.jsonl"
    c.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in cand))
    export_csv(SimpleNamespace(candidates=c, csv=v))
    rows = list(csv.reader(v.open(encoding="utf-8-sig")))
    assert rows[0] == CSV_COLS and rows[1][2] == "교사1" and rows[2][2] == "모델2" and rows[1][3] == ""
    rows[2][3], rows[3][4] = "고친2", "제외 — 원문 오류"
    csv.writer(v.open("w", encoding="utf-8-sig", newline="")).writerows(rows)
    import_csv(SimpleNamespace(candidates=c, csv=v, out=o))
    got = [json.loads(l) for l in o.open()]
    assert [(g["id"], g["ref"], g["edited"]) for g in got] == [("e001", "교사1", False), ("e002", "고친2", True)]
    rows[1][1] = "바뀐 원문"
    csv.writer(v.open("w", encoding="utf-8-sig", newline="")).writerows(rows)
    with pytest.raises(SystemExit, match="원문"):
        import_csv(SimpleNamespace(candidates=c, csv=v, out=o))


def test_build_v2_references_and_rejects_copies(tmp_path):
    import csv as _csv, json as _json, types
    import pytest
    from training.eval_set import build_v2
    v1 = tmp_path / "v1.jsonl"
    v1.write_text(_json.dumps({"id": "e001", "src": "원문 하나", "ref": "옛 정답", "stratum": "general", "doc_id": "d1"}, ensure_ascii=False) + "\n", encoding="utf-8")
    cand = tmp_path / "cand.jsonl"
    cand.write_text("".join(_json.dumps(r, ensure_ascii=False) + "\n" for r in [
        {"id": "e001", "src": "원문 하나", "teacher": "교사1"}, {"id": "e002", "src": "표 조각", "teacher": "교사2"}]), encoding="utf-8")
    fill = tmp_path / "fill.jsonl"
    fill.write_text(_json.dumps({"id": "e002", "doc_id": "d2", "idx": 3, "stratum": "general", "src": "새 원문", "teacher": "교사3"}, ensure_ascii=False) + "\n", encoding="utf-8")

    def write(rows):
        p = tmp_path / "review.csv"
        with p.open("w", encoding="utf-8-sig", newline="") as fh:
            w = _csv.writer(fh)
            w.writerow(["id", "원문", "정답1", "정답2", "메모"])
            w.writerows(rows)
        return p
    out = tmp_path / "out.jsonl"
    a = types.SimpleNamespace(v1=v1, candidates=cand, fill=fill, csv=write([["e002", "새 원문", "가", "나", ""], ["e001", "원문 하나", "다", "라", ""]]), out=out)
    build_v2(a)
    got = [_json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]
    assert [g["id"] for g in got] == ["e001", "e002"] and got[0]["references"] == ["다", "라"] and got[0]["ref_v1"] == "옛 정답"
    assert got[1]["replaced"] == "표 조각" and got[1]["idx"] == 3 and got[1]["teacher"] == "교사3"
    a.csv = write([["e001", "원문 하나", "원문 하나", "라", ""]])
    with pytest.raises(SystemExit):
        build_v2(a)
