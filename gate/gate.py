import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from gate.parity import check_parity


def evaluate(champion: dict, candidate: dict, thresholds: dict, first_champion=False) -> tuple[list[str], list[dict]]:
    old = champion.get("metrics", champion)
    new = candidate.get("metrics", candidate)
    if not isinstance(old, dict) or not isinstance(new, dict):
        return ["evaluation metrics must be objects"], []
    failures = []
    rows = []

    def metric(name):
        before, after = old.get(name), new.get(name)
        rows.append({"metric": name, "champion": before, "candidate": after})
        if not isinstance(before, (int, float)) or isinstance(before, bool) or not isinstance(after, (int, float)) or isinstance(after, bool):
            failures.append(f"{name}: missing or nonnumeric metric")
            return None, None
        return before, after

    for name, expected in thresholds["must_equal"].items():
        value = new.get(name)
        rows.append({"metric": name, "champion": old.get(name), "candidate": value})
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            failures.append(f"{name}: missing or nonnumeric metric")
        elif value != expected:
            failures.append(f"{name}: {value} must equal {expected}")
    if first_champion:
        for name, minimum in thresholds["first_champion"].items():
            value = new.get(name)
            rows.append({"metric": name, "champion": old.get(name), "candidate": value})
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                failures.append(f"{name}: missing or nonnumeric metric")
            elif value < minimum:
                failures.append(f"{name}: {value} is below first-champion minimum {minimum}")
    for name in thresholds["at_least_champion"]:
        if first_champion and name in thresholds["first_champion"]:
            continue
        if first_champion and not old:
            continue
        before, after = metric(name)
        if after is not None and after < before:
            failures.append(f"{name}: {after} is below champion {before}")
    if not first_champion or old:
        for name in thresholds["at_most_champion"]:
            before, after = metric(name)
            if after is not None and after > before:
                failures.append(f"{name}: {after} is above champion {before}")
        for name in thresholds["above_champion"]:
            before, after = metric(name)
            if after is not None and after <= before:
                failures.append(f"{name}: {after} must be above champion {before}")
    for name, maximum in thresholds["maximum"].items():
        value = new.get(name)
        rows.append({"metric": name, "champion": old.get(name), "candidate": value})
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            failures.append(f"{name}: missing or nonnumeric metric")
        elif value > maximum:
            failures.append(f"{name}: {value} exceeds limit {maximum}")
    return failures, rows


def run_gate(champion_version: str | None, candidate_version: str, models_dir="models", reports_dir="reports",
             thresholds_path=None, data_dir="data") -> dict:
    models_dir, reports_dir = Path(models_dir), Path(reports_dir)
    data_dir = Path(data_dir)
    thresholds_path = Path(thresholds_path or Path(__file__).with_name("thresholds.json"))
    reasons, rows = [], []
    first_champion = champion_version in (None, "", "dummy", "none")
    eval_set = data_dir / "eval" / "eval_set.jsonl"
    eval_set_sha1 = None
    evaluation_sets = {}
    # 게이트 실행마다 따로 둔다(dummy→v2와 v2→v3가 같은 evaluations/v2.json을 덮어쓰지 않게).
    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{champion_version or 'none'}-vs-{candidate_version}"
    run_dir = reports_dir / "evaluations" / run_id
    try:
        thresholds = json.loads(thresholds_path.read_text(encoding="utf-8"))
        if not eval_set.is_file():
            raise FileNotFoundError(f"evaluation set not found: {eval_set}")
        eval_set_sha1 = hashlib.sha1(eval_set.read_bytes()).hexdigest()
        from training.evaluate import evaluate as evaluate_model

        champion_metrics = {}
        if not first_champion:
            champion_metrics = evaluate_model(champion_version, eval_set, model_root=models_dir, data_dir=data_dir,
                                              with_bert=True, out=run_dir / f"{champion_version}.json")
        candidate_metrics = evaluate_model(candidate_version, eval_set, model_root=models_dir, data_dir=data_dir,
                                            with_bert=True, out=run_dir / f"{candidate_version}.json")
        after_sha1 = hashlib.sha1(eval_set.read_bytes()).hexdigest()
        champion_sha1 = champion_metrics.get("test_set_sha1") if not first_champion else eval_set_sha1
        candidate_sha1 = candidate_metrics.get("test_set_sha1")
        evaluation_sets = {"candidate": candidate_sha1}
        if not first_champion:
            evaluation_sets["champion"] = champion_sha1
        if champion_sha1 != candidate_sha1 or candidate_sha1 != eval_set_sha1 or after_sha1 != eval_set_sha1:
            reasons = ["evaluation set fingerprint differs between champion and candidate"]
        else:
            reasons, rows = evaluate(champion_metrics, candidate_metrics, thresholds, first_champion)
    except Exception as exc:
        reasons = [f"Unable to evaluate models on the shared evaluation set: {exc}"]
        thresholds = {}
    parity_errors = check_parity(candidate_version, models_dir)
    reasons.extend(f"parity: {error}" for error in parity_errors)
    result = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "champion": champion_version,
        "candidate": candidate_version,
        "eval_set_sha1": eval_set_sha1,
        "evaluations": f"evaluations/{run_id}",
        "evaluation_sets": evaluation_sets,
        "passed": not reasons,
        "reasons": reasons,
        "metrics": rows,
    }
    reports_dir.mkdir(parents=True, exist_ok=True)
    history_path = reports_dir / "model_history.jsonl"
    with history_path.open("a", encoding="utf-8") as history:
        history.write(json.dumps(result, ensure_ascii=False) + "\n")
    history = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines() if line]
    report = [f"# Model Gate Report", "", f"## {champion_version or 'none'} vs {candidate_version}", "",
              f"Evaluation set SHA-1: `{eval_set_sha1 or 'unavailable'}`"]
    report.extend(f"- {version}: `{fingerprint}`" for version, fingerprint in evaluation_sets.items())
    report.extend(["", "| 지표 | Champion | 후보 |", "|---|---:|---:|"])
    report.extend(f"| {row['metric']} | {row['champion']} | {row['candidate']} |" for row in rows)
    report.extend(["", f"**결과: {'PASS' if result['passed'] else 'FAIL'}**"])
    if reasons:
        report.extend(["", "### 이유", *[f"- {reason}" for reason in reasons]])
    report.extend(["", "## 지난 버전 이력", "", "| 시각 | Champion | 후보 | 결과 |", "|---|---|---|---|"])
    report.extend(f"| {item['evaluated_at']} | {item['champion'] or 'none'} | {item['candidate']} | {'PASS' if item['passed'] else 'FAIL'} |" for item in history)
    (reports_dir / "MODEL_REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Re-evaluate champion and candidate on the shared human-reviewed eval set")
    parser.add_argument("champion")
    parser.add_argument("candidate")
    parser.add_argument("--models-dir", default="models")
    parser.add_argument("--reports-dir", default="reports")
    parser.add_argument("--thresholds", default=None)
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args(argv)
    result = run_gate(args.champion, args.candidate, args.models_dir, args.reports_dir, args.thresholds, args.data_dir)
    print("PASS" if result["passed"] else "FAIL")
    for reason in result["reasons"]:
        print(f"- {reason}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
