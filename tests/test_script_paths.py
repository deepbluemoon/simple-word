import json
import os
import subprocess
import sys
from pathlib import Path


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
