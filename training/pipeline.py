"""자동 학습 파이프라인 (이슈 #8): 수집 → 전처리 → 교사 생성 → 검사 → (새 통과 짝이 충분하면) 학습 → export → evaluate → 게이트 → 후보 등록.

    python -m training.pipeline --data-only     # 매일: 수집~검사까지만
    python -m training.pipeline                 # 주 1회: 통과 짝이 직전 학습보다 --min-new-pairs 건 이상 늘었으면 학습까지
    python -m training.pipeline --force         # 건수와 상관없이 학습

- 단계마다 입력 지문(파일 sha1)을 data/pipeline_state.json에 남긴다. 입력이 그대로면 그 단계는 건너뛴다.
  그래서 다시 돌려도 같은 결과이고, 중간에 멈췄으면 멈춘 단계부터 이어서 한다.
- 학습~게이트는 한 버전(run)으로 묶는다. 새 버전 이름은 models/ 아래 v<N> 다음 번호.
  게이트가 끝나면(통과·탈락 모두) 그 run을 닫고 last_train에 통과 짝 수를 남긴다 → 다음 학습 기준.
- 실패하면 어느 단계인지 보고서와 state에 남기고 멈춘다(종료 코드 1).
- 결과 요약: reports/pipeline-<날짜>.json
- 게이트 통과 시 models/registry.json에 canary 후보(weight 0)로 적는 데까지만. 업로드·배포는 배포 단계에서.
"""
import argparse
import datetime as dt
import hashlib
import json
import re
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

DEFAULT_MIN_NEW_PAIRS = 200
DATA_STAGES = ("collect", "preprocess", "teacher", "check")


def sha1(path: Path) -> str | None:
    path = Path(path)
    if not path.is_file():
        return None
    h = hashlib.sha1()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def count_passed(pairs_path: Path) -> int:
    pairs_path = Path(pairs_path)
    if not pairs_path.is_file():
        return 0
    return sum(1 for line in pairs_path.open(encoding="utf-8") if line.strip() and json.loads(line).get("passed"))


@dataclass
class Context:
    data_dir: Path
    models_dir: Path
    reports_dir: Path
    raw_dir: Path
    today: str
    force: bool = False
    min_new_pairs: int = DEFAULT_MIN_NEW_PAIRS
    state: dict = field(default_factory=dict)
    log: Callable = print

    @property
    def state_path(self) -> Path:
        return self.data_dir / "pipeline_state.json"

    @property
    def registry_path(self) -> Path:
        return self.models_dir / "registry.json"

    def stage_state(self, name) -> dict:
        return self.state.setdefault("stages", {}).setdefault(name, {})

    def save_state(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        tmp.replace(self.state_path)


class Stop(Exception):
    """정상 종료(학습할 만큼 새 짝이 없음 등). 뒤 단계는 not_run으로 남는다."""


@dataclass
class Stage:
    """done(ctx) → 이미 한 일이면 True(건너뜀). run(ctx) → 결과 요약 dict. Stop을 던지면 거기서 정상 종료."""
    name: str
    run: Callable[[Context], dict | None]
    done: Callable[[Context], bool] = lambda ctx: False


# ---------- 데이터 단계: 입력 지문이 같으면 건너뜀 ----------

def _fingerprint_stage(name, inputs: Callable[[Context], dict], work: Callable[[Context], dict]) -> Stage:
    """입력 지문이 지난번 성공 때와 같으면 건너뜀. 지문은 실행 뒤에 잡는다(check는 자기 입력 pairs.jsonl을 고쳐 쓴다)."""
    def done(ctx):
        recorded = ctx.stage_state(name).get("inputs")
        return recorded is not None and recorded == inputs(ctx)

    def run(ctx):
        result = work(ctx) or {}
        ctx.stage_state(name).update({"inputs": inputs(ctx), "at": _now(), "result": result})
        return result

    return Stage(name, run, done)


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _collect(ctx):
    from training.collect import collect
    return {"added": collect(ctx.data_dir, ctx.raw_dir, log=ctx.log)}


def _preprocess(ctx):
    from training.preprocess import preprocess
    stats = preprocess(ctx.data_dir)
    return {"docs": stats["docs"], "sentences": stats["sentences"]}


def _teacher(ctx):
    from training.teacher import run
    return {"new_pairs": run(ctx.data_dir, log=ctx.log)}


def _check(ctx):
    from training.checks import recheck
    passed, total, reasons = recheck(ctx.data_dir)
    return {"passed": passed, "total": total, "reject_reasons": reasons}


def data_stages() -> list[Stage]:
    f = lambda name: lambda ctx: sha1(ctx.data_dir / name)
    return [
        # 수집은 하루 한 번. 입력 = 날짜
        _fingerprint_stage("collect", lambda ctx: {"date": ctx.today}, _collect),
        _fingerprint_stage("preprocess", lambda ctx: {"docs": f("docs.jsonl")(ctx)}, _preprocess),
        _fingerprint_stage("teacher", lambda ctx: {"sentences": f("sentences.jsonl")(ctx)}, _teacher),
        # 검사 규칙(checks.py)을 바꿔도 다시 돈다. 출력이 pairs.jsonl 자신이라 실행 뒤 지문을 남긴다
        _fingerprint_stage("check", lambda ctx: {"pairs": f("pairs.jsonl")(ctx), "rules": sha1(Path(__file__).with_name("checks.py"))}, _check),
    ]


# ---------- 학습 단계: run(버전) 하나로 묶음 ----------

def baseline_passed(ctx) -> int:
    """직전 학습에 쓴 통과 짝 수. state가 없으면 지금 champion의 학습 분할 크기로 대신한다."""
    last = ctx.state.get("last_train")
    if last:
        return last["passed_pairs"]
    from gate.registry import read_registry
    champion = read_registry(ctx.registry_path)["champion"]
    tm = ctx.models_dir / champion / "hf" / "train_metrics.json"
    if tm.is_file():
        return sum(json.loads(tm.read_text(encoding="utf-8")).get("sizes", {}).values())
    return 0


def next_version(models_dir: Path) -> str:
    nums = [int(m.group(1)) for p in Path(models_dir).glob("v*") if p.is_dir() and (m := re.fullmatch(r"v(\d+)", p.name))]
    return f"v{max(nums, default=0) + 1}"


def _decide(ctx):
    if ctx.state.get("run"):  # 지난번에 멈춘 run 이어서
        run = ctx.state["run"]
        ctx.log(f"이어서: {run['version']}")
        return {"resume": run["version"], "passed_pairs": run["passed_pairs"]}
    passed = count_passed(ctx.data_dir / "pairs.jsonl")
    base = baseline_passed(ctx)
    new = passed - base
    decision = {"passed_pairs": passed, "baseline": base, "new": new, "min_new_pairs": ctx.min_new_pairs, "force": ctx.force}
    if not ctx.force and new < ctx.min_new_pairs:
        ctx.stage_state("decide")["result"] = decision
        raise Stop(f"새 통과 짝 {new}건 < {ctx.min_new_pairs}건: 학습하지 않음")
    from gate.registry import read_registry
    ctx.state["run"] = {"version": next_version(ctx.models_dir), "passed_pairs": passed,
                        "champion": read_registry(ctx.registry_path)["champion"], "started_at": _now()}
    decision["version"] = ctx.state["run"]["version"]
    return decision


def _version(ctx):
    return ctx.state["run"]["version"]


def _train(ctx):
    from training.train import train
    eval_set = ctx.data_dir / "eval" / "eval_set.jsonl"
    m = train(_version(ctx), [str(ctx.data_dir / "pairs.jsonl")], data_root=ctx.data_dir, model_root=ctx.models_dir,
              split="time", docs=ctx.data_dir / "docs.jsonl", eval_set=eval_set if eval_set.is_file() else None)
    return {"best_epoch": m["best_epoch"], "sizes": m["sizes"], "train_seconds": m["train_seconds"]}


def _export(ctx):
    from training.export import export
    meta = export(_version(ctx), ctx.models_dir)
    return {"model_dir_mb": meta["metrics"]["model_dir_mb"]}


def _evaluate(ctx):
    from training.evaluate import evaluate
    v = _version(ctx)
    return evaluate(v, ctx.data_dir / v / "test.jsonl", model_root=ctx.models_dir, data_dir=ctx.data_dir)


def _gate(ctx):
    from gate.gate import run_gate
    run = ctx.state["run"]
    result = run_gate(run["champion"], run["version"], ctx.models_dir, ctx.reports_dir, data_dir=ctx.data_dir)
    run["gate"] = {"passed": result["passed"], "reasons": result["reasons"], "evaluated_at": result["evaluated_at"],
                   "champion": result["champion"], "candidate": result["candidate"]}
    return run["gate"]


def _register(ctx):
    run = ctx.state["run"]
    out = {"version": run["version"], "gate_passed": run["gate"]["passed"]}
    if run["gate"]["passed"]:
        from gate.registry import register_candidate
        register_candidate(run["version"], run["gate"], ctx.registry_path)
        out["registered"] = "canary(weight 0)"
    # run 닫기: 다음 학습은 이 통과 짝 수 기준
    ctx.state["last_train"] = {"version": run["version"], "passed_pairs": run["passed_pairs"],
                               "gate_passed": run["gate"]["passed"], "finished_at": _now()}
    ctx.state.pop("run")
    return out


def _meta_metrics(ctx):
    p = ctx.models_dir / _version(ctx) / "metadata.json"
    return json.loads(p.read_text(encoding="utf-8")).get("metrics", {}) if p.is_file() else {}


def train_stages() -> list[Stage]:
    mdir = lambda ctx: ctx.models_dir / _version(ctx)
    return [
        Stage("decide", _decide),
        Stage("train", _train, lambda ctx: (mdir(ctx) / "hf" / "train_metrics.json").is_file()),
        Stage("export", _export, lambda ctx: all((mdir(ctx) / f).is_file() for f in ("metadata.json", "encoder.onnx", "decoder.onnx", "parity.jsonl"))),
        Stage("evaluate", _evaluate, lambda ctx: "eval_model" in _meta_metrics(ctx)),
        Stage("gate", _gate, lambda ctx: "gate" in ctx.state["run"]),
        Stage("register", _register),
    ]


# ---------- 실행 ----------

def run_pipeline(stages: list[Stage], ctx: Context) -> dict:
    if ctx.state_path.is_file():
        ctx.state = json.loads(ctx.state_path.read_text(encoding="utf-8"))
    report = {"date": ctx.today, "started_at": _now(), "force": ctx.force, "min_new_pairs": ctx.min_new_pairs,
              "status": "ok", "failed_stage": None, "stages": []}
    pending = list(stages)
    while pending:
        stage = pending.pop(0)
        entry = {"name": stage.name}
        report["stages"].append(entry)
        t0 = time.time()
        try:
            if stage.done(ctx):
                entry["status"] = "skipped"
                ctx.log(f"[{stage.name}] 이미 함 — 건너뜀")
                continue
            ctx.log(f"[{stage.name}] 시작")
            entry["result"] = stage.run(ctx) or {}
            entry["status"] = "done"
        except Stop as stop:
            entry.update(status="stopped", reason=str(stop))
            report["status"] = "stopped"
            ctx.log(f"[{stage.name}] {stop}")
            break
        except Exception as exc:  # noqa: BLE001 — 어느 단계든 실패를 기록하고 멈춘다
            entry.update(status="failed", error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc(limit=5))
            report.update(status="failed", failed_stage=stage.name)
            ctx.state["last_failure"] = {"stage": stage.name, "error": entry["error"], "at": _now()}
            ctx.log(f"[{stage.name}] 실패: {entry['error']}")
            break
        finally:
            entry["seconds"] = round(time.time() - t0, 2)
            ctx.save_state()
    report["stages"].extend({"name": s.name, "status": "not_run"} for s in pending)
    if report["status"] != "failed":
        ctx.state.pop("last_failure", None)
    if ctx.state.get("run"):
        report["run"] = ctx.state["run"]
    report["last_train"] = ctx.state.get("last_train")
    report["finished_at"] = _now()
    ctx.save_state()
    ctx.reports_dir.mkdir(parents=True, exist_ok=True)
    path = ctx.reports_dir / f"pipeline-{ctx.today}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    report["path"] = str(path)
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="수집 → 전처리 → 교사 → 검사 → 학습 → export → evaluate → 게이트 → 후보 등록")
    ap.add_argument("--data", default="data")
    ap.add_argument("--raw", default="raw")
    ap.add_argument("--models", default="models")
    ap.add_argument("--reports", default="reports")
    ap.add_argument("--min-new-pairs", type=int, default=DEFAULT_MIN_NEW_PAIRS, help="직전 학습보다 통과 짝이 이만큼 늘어야 학습")
    ap.add_argument("--force", action="store_true", help="새 짝 수와 상관없이 학습")
    ap.add_argument("--data-only", action="store_true", help="수집~검사까지만 (매일 크론)")
    a = ap.parse_args(argv)
    ctx = Context(Path(a.data), Path(a.models), Path(a.reports), Path(a.raw),
                  today=dt.date.today().isoformat(), force=a.force, min_new_pairs=a.min_new_pairs)
    stages = data_stages() + ([] if a.data_only else train_stages())
    report = run_pipeline(stages, ctx)
    print(json.dumps({k: report[k] for k in ("status", "failed_stage", "path")}, ensure_ascii=False))
    return 1 if report["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
