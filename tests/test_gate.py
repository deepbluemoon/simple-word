import json

from gate.gate import run_gate
from gate.parity import check_parity


def make_model(models_dir, version, metrics, expected="입력"):
    artifact = models_dir / version
    artifact.mkdir(parents=True)
    (artifact / "metadata.json").write_text(json.dumps({"version": version, "metrics": metrics}))
    (artifact / "parity.jsonl").write_text(json.dumps({"input": "입력", "output": expected}) + "\n")


def metrics(sari=0.8, number_rate=1.0, latency=500):
    return {
        "number_date_amount_match_rate": number_rate,
        "preserved_terms_retention_rate": 1.0,
        "bert_score": 0.9,
        "difficult_term_retention_rate": 0.1,
        "sentence_length_reduction_rate": 0.2,
        "sari": sari,
        "cpu_p95_ms_per_sentence": latency,
        "model_memory_mb": 200,
    }


def test_parity_reports_exact_match_and_mismatch(tmp_path):
    make_model(tmp_path, "ok", metrics())
    make_model(tmp_path, "bad", metrics(), expected="다른 출력")

    assert check_parity("ok", tmp_path) == []
    assert "expected" in check_parity("bad", tmp_path)[0]


def test_gate_records_pass_report_and_history(tmp_path):
    models_dir, reports_dir = tmp_path / "models", tmp_path / "reports"
    models_dir.mkdir()
    make_model(models_dir, "champion", metrics())
    make_model(models_dir, "candidate", metrics(sari=0.81))

    result = run_gate("champion", "candidate", models_dir, reports_dir)

    assert result["passed"]
    assert len((reports_dir / "model_history.jsonl").read_text().splitlines()) == 1
    report = (reports_dir / "MODEL_REPORT.md").read_text()
    assert "champion vs candidate" in report
    assert "## 지난 버전 이력" in report


def test_gate_fails_thresholds_and_parity_with_reasons(tmp_path):
    models_dir, reports_dir = tmp_path / "models", tmp_path / "reports"
    models_dir.mkdir()
    make_model(models_dir, "champion", metrics())
    make_model(models_dir, "candidate", metrics(sari=0.7, number_rate=0.99, latency=1100), expected="불일치")

    result = run_gate("champion", "candidate", models_dir, reports_dir)

    assert not result["passed"]
    assert any("number_date_amount_match_rate" in reason for reason in result["reasons"])
    assert any("sari" in reason for reason in result["reasons"])
    assert any("cpu_p95_ms_per_sentence" in reason for reason in result["reasons"])
    assert any("parity" in reason for reason in result["reasons"])
