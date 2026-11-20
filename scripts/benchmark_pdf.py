#!/usr/bin/env python3
"""Measure PDF extraction latency and worker RSS with a loaded champion model.

Run in the serving image/host with the real model registry mounted:
python scripts/benchmark_pdf.py sample.pdf --expected-model v2 --runs 5
"""
import argparse
import multiprocessing
import resource
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api import main as api_main


def process_rss_kb(pid: int) -> int:
    result = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True)
    return int(result.stdout.strip() or 0) if result.returncode == 0 else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--expected-model", default="v2")
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args(argv)
    versions = {item["version"]: item["roles"] for item in api_main.router.health()["model_versions"]}
    if "champion" not in versions.get(args.expected_model, []):
        parser.error(f"expected champion {args.expected_model!r} is not loaded: {versions}")
    if args.runs < 1:
        parser.error("--runs must be positive")
    data = args.pdf.read_bytes()
    durations, child_peak_rss = [], 0
    for _ in range(args.runs):
        error = []
        started = time.perf_counter()
        worker = threading.Thread(target=lambda: _capture(error, data))
        worker.start()
        while worker.is_alive():
            child_peak_rss = max(
                child_peak_rss,
                *(process_rss_kb(child.pid) for child in multiprocessing.active_children()),
                0,
            )
            worker.join(0.02)
        durations.append(time.perf_counter() - started)
        if error:
            raise error[0]
    parent_peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    parent_peak_mb = parent_peak / (1024 * 1024 if sys_platform_is_macos() else 1024)
    print(f"model={args.expected_model} runs={args.runs} bytes={len(data)}")
    print(f"latency_median_seconds={statistics.median(durations):.3f} latency_max_seconds={max(durations):.3f}")
    print(f"parent_peak_rss_mb={parent_peak_mb:.1f} pdf_worker_peak_rss_mb={child_peak_rss / 1024:.1f}")


def _capture(errors, data):
    try:
        api_main.extract_pdf_text(data)
    except Exception as exc:
        errors.append(exc)


def sys_platform_is_macos():
    import sys
    return sys.platform == "darwin"


if __name__ == "__main__":
    main()
