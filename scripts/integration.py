#!/usr/bin/env python3
"""Run the local Docker Compose integration checks for issue #16."""
import concurrent.futures
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RUN_ID = uuid.uuid4().hex[:8]
COMPOSE = ["docker", "compose", "-p", f"simpleword-integration-{RUN_ID}", "-f", "deploy/compose.yaml"]
WORK = ROOT / ".tmp" / f"integration-{RUN_ID}"


def request(url, data=None, headers=None, timeout=10):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data, headers or {}), timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as response:
        return response.code, response.read()


def multipart(filename, content, content_type="text/plain"):
    boundary = uuid.uuid4().hex
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
            f"Content-Type: {content_type}\r\n\r\n").encode() + content + f"\r\n--{boundary}--\r\n".encode()
    return body, {"Content-Type": f"multipart/form-data; boundary={boundary}"}


def docx():
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w") as archive:
        archive.writestr("word/document.xml", '<w:document xmlns:w="urn:w"><w:body><w:p><w:r><w:t>통합 테스트</w:t></w:r></w:p></w:body></w:document>')
    return result.getvalue()


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    models = WORK / "models"
    models.mkdir()
    versions = ("integration-v1", "integration-version-two")
    for version in versions:
        artifact = models / version
        artifact.mkdir()
        (artifact / "metadata.json").write_text(json.dumps({"version": version}), encoding="utf-8")
    (models / "registry.json").write_text('{"champion":"integration-v1"}', encoding="utf-8")
    while True:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        if port != 8000:
            break
    env = os.environ | {"HOST_PORT": str(port), "MODEL_DIR": str(models), "MAX_CONCURRENT_SIMPLIFY": "1"}
    url = f"http://127.0.0.1:{port}"
    try:
        subprocess.run(COMPOSE + ["up", "-d", "--build"], cwd=ROOT, env=env, check=True)
        deadline = time.monotonic() + 90
        while True:
            try:
                status, _ = request(url + "/health", timeout=2)
                if status == 200:
                    break
            except (OSError, urllib.error.URLError):
                pass
            if time.monotonic() >= deadline:
                raise RuntimeError("API did not become healthy")
            time.sleep(1)
        print("PASS /health")
        subprocess.run([sys.executable, str(ROOT / "scripts" / "smoke.py"), url], cwd=ROOT, env=env, check=True)

        for filename, content, mime in (("sample.txt", "간단한 통합 테스트입니다.".encode(), "text/plain"),
                                        ("sample.docx", docx(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")):
            body, headers = multipart(filename, content, mime)
            status, payload = request(url + "/simplify", body, headers)
            assert status == 200 and json.loads(payload)["sentences"], f"{filename}: HTTP {status} {payload!r}"
            print(f"PASS upload {filename}")

        status, payload = request(url + "/feedback", json.dumps({"model_version": "integration-v1", "original": "a", "simple": "b", "vote": "up"}).encode(), {"Content-Type": "application/json"})
        assert status == 200 and json.loads(payload)["saved"]
        print("PASS /feedback")

        body, headers = multipart("load.txt", ("부하 테스트 문장입니다. " * 30000).encode())
        with concurrent.futures.ThreadPoolExecutor(max_workers=32) as pool:
            results = list(pool.map(lambda _: request(url + "/simplify", body, headers, timeout=60)[0], range(32)))
        assert 429 in results, f"expected overload 429, got statuses {sorted(set(results))}"
        print(f"PASS overload 429 ({results.count(429)}/32)")

        registry = models / "registry.json"
        for version in versions:
            registry.write_text(json.dumps({"champion": version}), encoding="utf-8")
            deadline = time.monotonic() + 10
            while True:
                status, payload = request(url + "/health")
                actual = json.loads(payload).get("model_versions", [{}])[0].get("version")
                if status == 200 and actual == version or time.monotonic() >= deadline:
                    break
                time.sleep(0.1)
            assert status == 200 and actual == version, f"registry expected {version}, got HTTP {status}: {payload!r}"
        print("PASS registry swap without restart")
    finally:
        subprocess.run(COMPOSE + ["down", "-v", "--remove-orphans"], cwd=ROOT, env=env, check=False)
        shutil.rmtree(WORK, ignore_errors=True)


if __name__ == "__main__":
    main()
