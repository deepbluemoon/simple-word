#!/usr/bin/env python3
"""v2 서빙 크기 측정: 시작→첫 /health 성공 시간, 유휴 메모리, 100문장 처리 중 최대 메모리, 지연 p95.

컨테이너(배포와 같은 이미지, --cpus 2):
  docker build -t simple-word:local .
  python scripts/footprint.py docker --image simple-word:local --models models --cpus 2 --sentences data/v2/test.jsonl
컨테이너 없이(같은 uvicorn 앱을 로컬 프로세스로):
  python scripts/footprint.py native --models models --sentences data/v2/test.jsonl

출력은 JSON 한 줄이다. 메모리는 MiB. docker 는 cgroup memory.current / memory.peak, native 는 프로세스 RSS 표본(50ms)이다.
"""
import argparse, json, math, os, subprocess, sys, threading, time, urllib.request, uuid
from pathlib import Path

PORT = 18077


def p95(xs):
    s = sorted(xs)
    return s[min(len(s) - 1, math.ceil(len(s) * 0.95) - 1)]


def post_txt(url, text, timeout=600):
    b = uuid.uuid4().hex
    body = (f"--{b}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.txt\"\r\n"
            f"Content-Type: text/plain\r\n\r\n").encode() + text.encode() + f"\r\n--{b}--\r\n".encode()
    req = urllib.request.Request(url, body, {"Content-Type": f"multipart/form-data; boundary={b}"})
    t = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.load(r)
    return time.perf_counter() - t, out


def wait_health(url, t0, limit=300):
    while time.perf_counter() - t0 < limit:
        try:
            with urllib.request.urlopen(url + "/health", timeout=2) as r:
                if r.status == 200:
                    return time.perf_counter() - t0, json.load(r)
        except Exception:
            pass
        time.sleep(0.05)
    raise SystemExit("health 시간 초과")


class Native:
    def __init__(self, a):
        env = {**os.environ, "REGISTRY_PATH": str(Path(a.models) / "registry.json"), "LOG_DIR": a.log_dir,
               "MAX_CONCURRENT_SIMPLIFY": "2"}
        self.t0 = time.perf_counter()
        self.p = subprocess.Popen([sys.executable, "-m", "uvicorn", "api.main:app", "--port", str(PORT)], env=env,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.peak = 0

    def mem(self):
        out = subprocess.run(["ps", "-o", "rss=", "-p", str(self.p.pid)], capture_output=True, text=True).stdout.strip()
        return int(out) / 1024 if out else 0.0

    def reset_peak(self):
        self.peak = 0

    def stop(self):
        self.p.terminate()
        self.p.wait()


class Docker:
    def __init__(self, a):
        self.name = f"sw-footprint-{uuid.uuid4().hex[:6]}"
        cmd = ["docker", "run", "-d", "--rm", "--name", self.name, "-p", f"{PORT}:8000", "--cpus", str(a.cpus),
               "-v", f"{Path(a.models).resolve()}:/app/models:ro", "-e", "LOG_DIR=/app/logs",
               "-e", "MAX_CONCURRENT_SIMPLIFY=2", a.image]
        self.t0 = time.perf_counter()  # docker run 호출 직전부터
        subprocess.run(cmd, check=True, capture_output=True)
        self.peak = 0

    def _cat(self, f):
        r = subprocess.run(["docker", "exec", self.name, "cat", f"/sys/fs/cgroup/{f}"], capture_output=True, text=True)
        return int(r.stdout) / 2**20 if r.returncode == 0 and r.stdout.strip().isdigit() else None

    def mem(self):
        return self._cat("memory.current") or 0.0

    def reset_peak(self):
        self.peak = 0

    def kernel_peak(self):
        return self._cat("memory.peak")

    def stop(self):
        subprocess.run(["docker", "stop", self.name], capture_output=True)


def sampler(target, stop):
    while not stop.is_set():
        target.peak = max(target.peak, target.mem())
        time.sleep(0.05)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["docker", "native"])
    ap.add_argument("--image", default="simple-word:local")
    ap.add_argument("--models", default="models", help="registry.json 과 v2/ 가 있는 폴더")
    ap.add_argument("--cpus", default="2")
    ap.add_argument("--sentences", default="data/v2/test.jsonl", help="src 필드 jsonl. 앞 100문장을 쓴다")
    ap.add_argument("--log-dir", default=".tmp/footprint-logs")
    ap.add_argument("--rounds", type=int, default=3, help="100문장 문서 요청 횟수")
    a = ap.parse_args()
    sents = [json.loads(l)["src"] for l in open(a.sentences, encoding="utf-8")][:100]
    url = f"http://127.0.0.1:{PORT}"
    t = (Docker if a.mode == "docker" else Native)(a)
    try:
        ready_s, health = wait_health(url, t.t0)
        post_txt(url + "/simplify", sents[0])  # 첫 요청(지연 로딩 등) 한 번 치르고
        time.sleep(3)
        idle = t.mem()
        stop = threading.Event()
        th = threading.Thread(target=sampler, args=(t, stop), daemon=True)
        th.start()
        doc = []
        for _ in range(a.rounds):  # 100문장 문서 1건씩
            s, out = post_txt(url + "/simplify", "\n".join(sents))
            doc.append(s)
        assert len(out["sentences"]) == len(sents), len(out["sentences"])
        one = [post_txt(url + "/simplify", s)[0] for s in sents]  # 1문장 요청 100건, 순차
        two = []  # 동시 2건(MAX_CONCURRENT_SIMPLIFY=2): 1문장 요청 100건을 두 스레드로
        lock = threading.Lock()

        def worker(chunk):
            for s in chunk:
                d = post_txt(url + "/simplify", s)[0]
                with lock:
                    two.append(d)
        ws = [threading.Thread(target=worker, args=(sents[i::2],)) for i in range(2)]
        [w.start() for w in ws]
        [w.join() for w in ws]
        stop.set()
        th.join()
        res = {"mode": a.mode, "cpus": a.cpus if a.mode == "docker" else f"host {os.cpu_count()}",
               "champion": health.get("champion") or health, "ready_s": round(ready_s, 2),
               "idle_mib": round(idle, 1), "peak_mib_sampled": round(t.peak, 1),
               "doc100_s": [round(x, 2) for x in doc], "doc100_ms_per_sentence": round(min(doc) / len(sents) * 1000, 1),
               "req1_p50_ms": round(sorted(one)[len(one) // 2] * 1000, 1), "req1_p95_ms": round(p95(one) * 1000, 1),
               "req1_conc2_p95_ms": round(p95(two) * 1000, 1)}
        if a.mode == "docker":
            res["peak_mib_cgroup"] = t.kernel_peak()  # 시작부터의 최대(로딩 포함)
        print(json.dumps(res, ensure_ascii=False))
    finally:
        t.stop()


if __name__ == "__main__":
    main()
