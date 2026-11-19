#!/usr/bin/env python3
"""Report latency distribution and HTTP 429 rate for concurrent simplify requests."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import math
import time
import urllib.error
import urllib.request


def percentile_ms(latencies, percentile):
    ordered = sorted(latencies)
    return ordered[min(len(ordered) - 1, math.ceil(len(ordered) * percentile) - 1)] * 1000


def threshold_failures(p95_ms, rate_429, max_p95_ms=None, max_429_rate=None):
    failures = []
    if max_p95_ms is not None and p95_ms > max_p95_ms:
        failures.append(f"p95 {p95_ms:.1f} ms exceeds {max_p95_ms:.1f} ms")
    if max_429_rate is not None and rate_429 > max_429_rate:
        failures.append(f"429 rate {rate_429:.1%} exceeds {max_429_rate:.1%}")
    return failures


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:18016/simplify")
    parser.add_argument("-n", "--requests", type=int, default=100)
    parser.add_argument("-c", "--concurrency", type=int, default=20)
    parser.add_argument("--max-p95-ms", type=float)
    parser.add_argument("--max-429-rate", type=float, help="maximum fraction from 0 to 1")
    args = parser.parse_args()
    if args.requests < 1 or args.concurrency < 1:
        parser.error("requests and concurrency must be positive")
    if args.max_p95_ms is not None and args.max_p95_ms <= 0:
        parser.error("max-p95-ms must be positive")
    if args.max_429_rate is not None and not 0 <= args.max_429_rate <= 1:
        parser.error("max-429-rate must be between 0 and 1")
    boundary = "simplewordloadtest"
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="load.txt"\r\n'
            f'Content-Type: text/plain\r\n\r\n').encode() + b"Concurrent load check. " * 100 + f"\r\n--{boundary}--\r\n".encode()
    latencies, statuses = [], []

    def send(_):
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(urllib.request.Request(args.url, body, {"Content-Type": f"multipart/form-data; boundary={boundary}"}), timeout=60) as response:
                status = response.status
                response.read()
        except urllib.error.HTTPError as response:
            status = response.code
            response.read()
        except (OSError, urllib.error.URLError):
            status = 0
        return time.perf_counter() - started, status

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        for latency, status in pool.map(send, range(args.requests)):
            latencies.append(latency)
            statuses.append(status)
    p95_ms = percentile_ms(latencies, .95)
    rate_429 = statuses.count(429) / len(statuses)
    unexpected = sum(status != 429 and not 200 <= status < 300 for status in statuses)
    print(f"requests={len(statuses)} concurrency={args.concurrency}")
    print(f"latency_ms min={min(latencies)*1000:.1f} p50={percentile_ms(latencies, .50):.1f} p95={p95_ms:.1f} p99={percentile_ms(latencies, .99):.1f} max={max(latencies)*1000:.1f}")
    print(f"429={statuses.count(429)} ({rate_429:.1%}); other_non_2xx={unexpected}")
    failures = threshold_failures(p95_ms, rate_429, args.max_p95_ms, args.max_429_rate)
    if unexpected:
        failures.append(f"{unexpected} unexpected non-2xx responses")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
