import shutil, subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")
def test_web_core_pure_functions():
    """web/core.js 순수 함수(오류 번역, 요약 계산) — 본문은 tests/web/core.test.js."""
    r = subprocess.run(["node", "--test", str(Path(__file__).parent / "web" / "core.test.js")], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
