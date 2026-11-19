import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from gate.parity import check_parity


def evaluate(champion: dict, candidate: dict, thresholds: dict, first_champion=False) -> tuple[list[str], list[dict]]:
    old = champion.get("metrics", {})
    new = candidate.get("metrics", {})
    if not isinstance(old, dict) or not isinstance(new, dict):
        return ["metadata metrics must be objects"], []
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


def run_gate(champion_version: str | None, candidate_version: str, models_dir="models", reports_dir="reports", thresholds_path=None) -> dict:
    models_dir, reports_dir = Path(models_dir), Path(reports_dir)
    thresholds_path = Path(thresholds_path or Path(__file__).with_name("thresholds.json"))
    reasons, rows = [], []
    first_champion = champion_version in (None, "", "dummy", "none")
    try:
        champion_path = models_dir / (champion_version or "") / "metadata.json"
        champion = (
            json.loads(champion_path.read_text(encoding="utf-8"))
            if not first_champion or champion_path.is_file()
            else {}
        )
        candidate = json.loads((models_dir / candidate_version / "metadata.json").read_text(encoding="utf-8"))
        thresholds = json.loads(thresholds_path.read_text(encoding="utf-8"))
        reasons, rows = evaluate(champion, candidate, thresholds, first_champion)
    except (OSError, ValueError, KeyError) as exc:
        reasons = [f"Unable to read metadata or thresholds: {exc}"]
        thresholds = {}
    parity_errors = check_parity(candidate_version, models_dir)
    reasons.extend(f"parity: {error}" for error in parity_errors)
    result = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "champion": champion_version,
        "candidate": candidate_version,
        "passed": not reasons,
        "reasons": reasons,
        "metrics": rows,
    }
    reports_dir.mkdir(parents=True, exist_ok=True)
    history_path = reports_dir / "model_history.jsonl"
    with history_path.open("a", encoding="utf-8") as history:
        history.write(json.dumps(result, ensure_ascii=False) + "\n")
    history = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines() if line]
    report = [f"# Model Gate Report", "", f"## {champion_version or 'none'} vs {candidate_version}", "", "| 지표 | Champion | 후보 |", "|---|---:|---:|"]
    report.extend(f"| {row['metric']} | {row['champion']} | {row['candidate']} |" for row in rows)
    report.extend(["", f"**결과: {'PASS' if result['passed'] else 'FAIL'}**"])
    if reasons:
        report.extend(["", "### 이유", *[f"- {reason}" for reason in reasons]])
    report.extend(["", "## 지난 버전 이력", "", "| 시각 | Champion | 후보 | 결과 |", "|---|---|---|---|"])
    report.extend(f"| {item['evaluated_at']} | {item['champion'] or 'none'} | {item['candidate']} | {'PASS' if item['passed'] else 'FAIL'} |" for item in history)
    (reports_dir / "MODEL_REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Compare a candidate model with champion")
    parser.add_argument("champion")
    parser.add_argument("candidate")
    parser.add_argument("--models-dir", default="models")
    parser.add_argument("--reports-dir", default="reports")
    parser.add_argument("--thresholds", default=None)
    args = parser.parse_args(argv)
    result = run_gate(args.champion, args.candidate, args.models_dir, args.reports_dir, args.thresholds)
    print("PASS" if result["passed"] else "FAIL")
    for reason in result["reasons"]:
        print(f"- {reason}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
