import json

import pytest

from gate.registry import read_registry, register_candidate
from training import pipeline
from training.pipeline import Context, Stage, Stop, run_pipeline


def ctx_for(tmp_path, **kw):
    return Context(tmp_path / "data", tmp_path / "models", tmp_path / "reports", tmp_path / "raw",
                   today="2026-11-19", log=lambda *_: None, **kw)


def write_pairs(path, passed, failed=0):
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [{"src": f"s{i}", "tgt": "t", "passed": True} for i in range(passed)]
    rows += [{"src": f"f{i}", "tgt": "t", "passed": False} for i in range(failed)]
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def counting_stage(name, calls, inputs=None):
    """입력 지문이 바뀌지 않으면 건너뛰는 가짜 데이터 단계."""
    def work(ctx):
        calls.append(name)
        return {"n": len(calls)}
    return pipeline._fingerprint_stage(name, inputs or (lambda ctx: {"date": ctx.today}), work)


def test_fingerprint_stage_skips_when_inputs_unchanged(tmp_path):
    calls = []
    src = tmp_path / "data" / "in.txt"
    src.parent.mkdir(parents=True)
    src.write_text("a")
    stages = lambda: [counting_stage("collect", calls),
                      counting_stage("preprocess", calls, lambda ctx: {"in": pipeline.sha1(src)})]

    first = run_pipeline(stages(), ctx_for(tmp_path))
    second = run_pipeline(stages(), ctx_for(tmp_path))
    assert calls == ["collect", "preprocess"]
    assert [s["status"] for s in first["stages"]] == ["done", "done"]
    assert [s["status"] for s in second["stages"]] == ["skipped", "skipped"]

    src.write_text("b")  # 입력이 바뀐 단계만 다시
    run_pipeline(stages(), ctx_for(tmp_path))
    assert calls == ["collect", "preprocess", "preprocess"]

    run_pipeline(stages(), Context(**{**ctx_for(tmp_path).__dict__, "today": "2026-11-20"}))
    assert calls[-1] == "collect"  # 날짜가 바뀌면 수집 다시


def test_failure_records_stage_and_stops(tmp_path):
    ran = []

    def boom(ctx):
        raise RuntimeError("ollama down")

    stages = [Stage("collect", lambda ctx: ran.append("collect")), Stage("teacher", boom), Stage("check", lambda ctx: ran.append("check"))]
    ctx = ctx_for(tmp_path)
    report = run_pipeline(stages, ctx)

    assert ran == ["collect"]
    assert report["status"] == "failed" and report["failed_stage"] == "teacher"
    assert [s["status"] for s in report["stages"]] == ["done", "failed", "not_run"]
    assert "ollama down" in report["stages"][1]["error"]
    saved = json.loads((tmp_path / "reports" / "pipeline-2026-11-19.json").read_text())
    assert saved["failed_stage"] == "teacher"
    assert json.loads(ctx.state_path.read_text())["last_failure"]["stage"] == "teacher"

    ok = run_pipeline([Stage("collect", lambda ctx: None)], ctx_for(tmp_path))  # 성공하면 실패 기록 지움
    assert ok["status"] == "ok" and "last_failure" not in json.loads(ctx.state_path.read_text())


def test_main_returns_1_on_failure(tmp_path, monkeypatch):
    def boom(ctx):
        raise RuntimeError("x")
    monkeypatch.setattr(pipeline, "data_stages", lambda: [Stage("collect", boom)])
    code = pipeline.main(["--data", str(tmp_path / "d"), "--reports", str(tmp_path / "r"), "--models", str(tmp_path / "m"), "--data-only"])
    assert code == 1


def fake_train_stages(calls, gate_pass=True):
    """학습~등록을 가짜로: 실제 _decide·_register는 그대로 쓰고 무거운 단계만 바꾼다."""
    def mark(name):
        def run(ctx):
            calls.append(name)
            d = ctx.models_dir / ctx.state["run"]["version"]
            d.mkdir(parents=True, exist_ok=True)
            (d / name).write_text("ok")
        return run

    def done(name):
        return lambda ctx: (ctx.models_dir / ctx.state["run"]["version"] / name).is_file()

    def gate(ctx):
        calls.append("gate")
        run = ctx.state["run"]
        run["gate"] = {"passed": gate_pass, "reasons": [] if gate_pass else ["sari"], "candidate": run["version"],
                       "champion": run["champion"], "evaluated_at": "t"}
        return run["gate"]

    return [Stage("decide", pipeline._decide),
            *[Stage(n, mark(n), done(n)) for n in ("train", "export", "evaluate")],
            Stage("gate", gate, lambda ctx: "gate" in ctx.state["run"]),
            Stage("register", pipeline._register)]


def test_training_only_when_enough_new_pairs(tmp_path):
    calls = []
    pairs = tmp_path / "data" / "pairs.jsonl"
    write_pairs(pairs, passed=150, failed=40)

    report = run_pipeline(fake_train_stages(calls), ctx_for(tmp_path, min_new_pairs=200))
    assert calls == [] and report["status"] == "stopped"
    assert report["stages"][0]["status"] == "stopped" and "150" in report["stages"][0]["reason"]

    write_pairs(pairs, passed=250)
    report = run_pipeline(fake_train_stages(calls), ctx_for(tmp_path, min_new_pairs=200))
    assert calls == ["train", "export", "evaluate", "gate"]
    assert report["status"] == "ok" and report["last_train"]["passed_pairs"] == 250
    reg = read_registry(tmp_path / "models" / "registry.json")
    assert reg["canary"] == "v1" and reg["canary_weight"] == 0 and reg["champion"] == "dummy"
    assert reg["candidate"]["status"] == "pending_canary"

    write_pairs(pairs, passed=400)  # 직전 학습(250)보다 150건만 늘어 학습 안 함
    run_pipeline(fake_train_stages(calls), ctx_for(tmp_path, min_new_pairs=200))
    assert calls.count("train") == 1

    run_pipeline(fake_train_stages(calls), ctx_for(tmp_path, min_new_pairs=200, force=True))
    assert calls.count("train") == 2 and (tmp_path / "models" / "v2").is_dir()


def test_baseline_comes_from_champion_train_metrics_without_state(tmp_path):
    ctx = ctx_for(tmp_path)
    hf = tmp_path / "models" / "v2" / "hf"
    hf.mkdir(parents=True)
    (hf / "train_metrics.json").write_text(json.dumps({"sizes": {"train": 1800, "valid": 150, "test": 103}}))
    (tmp_path / "models" / "registry.json").write_text(json.dumps({"champion": "v2"}))
    assert pipeline.baseline_passed(ctx) == 2053
    assert pipeline.next_version(tmp_path / "models") == "v3"


def test_failed_training_resumes_same_version_and_skips_done_stages(tmp_path):
    calls = []
    write_pairs(tmp_path / "data" / "pairs.jsonl", passed=300)
    stages = fake_train_stages(calls)
    flaky = {"n": 0}
    real_eval = stages[3].run

    def eval_once_fails(ctx):
        flaky["n"] += 1
        if flaky["n"] == 1:
            raise RuntimeError("onnx not int8")
        return real_eval(ctx)

    stages[3] = Stage("evaluate", eval_once_fails, stages[3].done)
    first = run_pipeline(stages, ctx_for(tmp_path))
    assert first["failed_stage"] == "evaluate" and first["run"]["version"] == "v1"

    second = run_pipeline(stages, ctx_for(tmp_path))
    status = {s["name"]: s["status"] for s in second["stages"]}
    assert status == {"decide": "done", "train": "skipped", "export": "skipped", "evaluate": "done", "gate": "done", "register": "done"}
    assert calls == ["train", "export", "evaluate", "gate"]
    assert not (tmp_path / "models" / "v2").exists()


def test_failed_gate_closes_run_without_registering(tmp_path):
    calls = []
    write_pairs(tmp_path / "data" / "pairs.jsonl", passed=300)
    report = run_pipeline(fake_train_stages(calls, gate_pass=False), ctx_for(tmp_path))
    assert report["status"] == "ok" and report["last_train"]["gate_passed"] is False
    assert not (tmp_path / "models" / "registry.json").exists()
    assert "run" not in json.loads((tmp_path / "data" / "pipeline_state.json").read_text())


def test_register_candidate_rules(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({"champion": "v2", "canary": None, "canary_weight": 0, "shadow": None}))
    with pytest.raises(ValueError):
        register_candidate("v3", {"passed": False, "candidate": "v3"}, path)
    with pytest.raises(ValueError):
        register_candidate("v2", {"passed": True, "candidate": "v2"}, path)
    first = register_candidate("v3", {"passed": True, "candidate": "v3", "champion": "v2"}, path)
    again = register_candidate("v3", {"passed": True, "candidate": "v3", "champion": "v2"}, path)
    assert first == again and again["champion"] == "v2" and again["canary"] == "v3"


def test_router_accepts_registry_with_candidate_block(tmp_path):
    from api.router import ModelRouter
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({"champion": "dummy", "canary": "dummy", "canary_weight": 0, "shadow": None,
                                "candidate": {"version": "dummy", "status": "pending_canary"}}))
    router = ModelRouter(path)
    router.reload_if_changed()
    assert router.registry["champion"] == "dummy" and router.registry["canary_weight"] == 0
