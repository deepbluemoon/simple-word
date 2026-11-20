import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _run(script, *args, cwd):
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    return subprocess.run([sys.executable, "-S", str(ROOT / "scripts" / script), *map(str, args)],
                          cwd=cwd, env=env, capture_output=True, text=True)


def test_benchmark_runs_from_outside_repo_without_pythonpath(tmp_path):
    source = tmp_path / "sentences.jsonl"
    source.write_text(json.dumps({"src": "간단한 문장입니다."}) + "\n", encoding="utf-8")
    result = _run("benchmark_decoding.py", tmp_path / "missing-model", source,
                  "--worker", "--beams", "1", "--num-beams", "2", cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["num_beams"] == 1


def test_regenerate_parity_help_imports_from_outside_repo_without_pythonpath(tmp_path):
    result = _run("regenerate_parity.py", "--help", cwd=tmp_path)
    assert result.returncode == 0, result.stderr


def test_int8_parity_regeneration_uses_onnx_without_hf_equality(tmp_path, monkeypatch):
    from scripts import regenerate_parity

    artifact = tmp_path / "models" / "v2"
    artifact.mkdir(parents=True)
    (artifact / "metadata.json").write_text(json.dumps({"decoding": {"num_beams": 4}}), encoding="utf-8")

    class Model:
        placeholders = False
        force_placeholders = False
        def __init__(self, _path): pass
        def simplify(self, _inputs): return ["onnx output"]

    monkeypatch.setattr(regenerate_parity, "PARITY_INPUTS", ["source"])
    monkeypatch.setattr(regenerate_parity, "Simplifier", Model)
    monkeypatch.setattr(regenerate_parity, "hf_reference_outputs", lambda *_args: pytest.fail("INT8 does not require fp32 equality"))
    monkeypatch.setattr(sys, "argv", ["regenerate_parity.py", "v2", "--models-dir", str(tmp_path / "models")])

    regenerate_parity.main()

    record = json.loads((artifact / "parity.jsonl").read_text(encoding="utf-8"))
    assert record == {"input": "source", "output": "onnx output"}
