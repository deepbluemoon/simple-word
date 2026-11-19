#!/usr/bin/env python3
"""Report latency distribution and HTTP 429 rate for concurrent simplify requests."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import time
import urllib.error
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:18016/simplify")
    parser.add_argument("-n", "--requests", type=int, default=100)
    parser.add_argument("-c", "--concurrency", type=int, default=20)
    args = parser.parse_args()
    if args.requests < 1 or args.concurrency < 1:
        parser.error("requests and concurrency must be positive")
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
    ordered = sorted(latencies)
    percentile = lambda p: ordered[min(len(ordered) - 1, int((len(ordered) - 1) * p))] * 1000
    print(f"requests={len(statuses)} concurrency={args.concurrency}")
    print(f"latency_ms min={ordered[0]*1000:.1f} p50={percentile(.50):.1f} p95={percentile(.95):.1f} p99={percentile(.99):.1f} max={ordered[-1]*1000:.1f}")
    print(f"429={statuses.count(429)} ({statuses.count(429)/len(statuses):.1%}); other_non_2xx={sum(s != 429 and not 200 <= s < 300 for s in statuses)}")


if __name__ == "__main__":
    main()
