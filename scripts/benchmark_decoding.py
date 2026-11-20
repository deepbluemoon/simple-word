"""Compare greedy and metadata-configured beam inference on the same JSONL inputs.

Example: python scripts/benchmark_decoding.py models/v3-base data/eval/eval_set.jsonl --num-beams 4
Reports per-sentence p95 and process peak RSS separately for each decoding mode.
"""
import argparse
import json
import math
import subprocess
import sys
import time
import resource
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def worker(model_dir, test_path, beams, rounds):
    from simple_word.model import Simplifier

    rows = [json.loads(line) for line in Path(test_path).read_text(encoding="utf-8").splitlines() if line]
    sentences = [row["src"] for row in rows]
    if not sentences:
        raise ValueError("benchmark input has no sentences")
    model = Simplifier(model_dir)
    model.num_beams = beams
    model.simplify_detailed([sentences[0]])  # warm up ONNX before collecting per-sentence latency
    latencies = []
    for _ in range(rounds):
        for sentence in sentences:
            start = time.perf_counter()
            model.simplify_detailed([sentence])
            latencies.append((time.perf_counter() - start) * 1000)
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_mib = peak / (1024 * 1024 if sys.platform == "darwin" else 1024)
    latencies.sort()
    p95 = latencies[math.ceil(len(latencies) * 0.95) - 1]
    return {"num_beams": beams, "sentences": len(sentences), "rounds": rounds,
            "p95_ms_per_sentence": round(p95, 1), "peak_rss_mib": round(peak_mib, 1),
            "p95_under_1000ms": p95 <= 1000, "peak_rss_under_300mib": peak_mib <= 300}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model_dir")
    parser.add_argument("test_jsonl")
    parser.add_argument("--num-beams", type=int, default=4)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--beams", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.num_beams < 2 or args.rounds < 1:
        parser.error("--num-beams must be at least 2 and --rounds at least 1")
    if args.worker:
        print(json.dumps(worker(args.model_dir, args.test_jsonl, args.beams, args.rounds)))
        return
    results = []
    for beams in (1, args.num_beams):
        run = subprocess.run([sys.executable, __file__, args.model_dir, args.test_jsonl, "--num-beams", str(args.num_beams),
                              "--rounds", str(args.rounds), "--worker", "--beams", str(beams)],
                             check=True, capture_output=True, text=True)
        results.append(json.loads(run.stdout))
    print(json.dumps({"greedy": results[0], "beam": results[1],
                      "p95_limit_ms": 1000, "peak_rss_limit_mib": 300,
                      "peak_rss_delta_mib": round(results[1]["peak_rss_mib"] - results[0]["peak_rss_mib"], 1)},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
