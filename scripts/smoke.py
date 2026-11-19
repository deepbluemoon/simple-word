#!/usr/bin/env python3
"""Check a deployed API's model health and numeric-safe text upload."""
import argparse
import json
from pathlib import Path
import sys
import time
import urllib.request
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from simple_word.numbers import numbers

SAMPLE_SENTENCES = (
    "2026년 11월 19일에 12명이 신청했습니다.",
    "지원 금액은 35,000원입니다.",
)


def validate(health, result):
    versions = health.get("model_versions") if isinstance(health, dict) else None
    if not isinstance(versions, list) or not any(isinstance(item, dict) and item.get("version") for item in versions):
        raise ValueError("/health did not report a model version")
    if not isinstance(result, dict) or not isinstance(result.get("model_version"), str) or not result["model_version"]:
        raise ValueError("/simplify did not report a model version")
    sentences = result.get("sentences")
    if not isinstance(sentences, list) or len(sentences) != len(SAMPLE_SENTENCES):
        raise ValueError(f"expected {len(SAMPLE_SENTENCES)} simplified sentences")
    for expected, item in zip(SAMPLE_SENTENCES, sentences):
        if not isinstance(item, dict) or not isinstance(item.get("fallback"), bool):
            raise ValueError("each simplified sentence must include a boolean fallback key")
        if numbers(item.get("original", "")) != numbers(expected) or numbers(item.get("simple", "")) != numbers(expected):
            raise ValueError("numeric values changed in the smoke sample")


def read_json(request, timeout=5):
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise ValueError(f"{request.full_url} returned HTTP {response.status}")
        return json.loads(response.read())


def upload_url(base, timeout=5):
    boundary = uuid.uuid4().hex
    content = "\n".join(SAMPLE_SENTENCES).encode("utf-8")
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"smoke.txt\"\r\n"
            f"Content-Type: text/plain; charset=utf-8\r\n\r\n").encode() + content + f"\r\n--{boundary}--\r\n".encode()
    request = urllib.request.Request(
        f"{base.rstrip('/')}/simplify",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    return read_json(request, timeout)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("address", help="deployed base URL, such as https://api.example.com")
    args = parser.parse_args(argv)
    base = args.address.rstrip("/")
    deadline = time.monotonic() + 5
    try:
        health = read_json(urllib.request.Request(f"{base}/health"), max(0.1, deadline - time.monotonic()))
        result = upload_url(base, max(0.1, deadline - time.monotonic()))
        validate(health, result)
        if time.monotonic() > deadline:
            raise TimeoutError("smoke check exceeded 5 seconds")
    except Exception as error:
        print(f"FAIL smoke: {error}", file=sys.stderr)
        return 1
    print(f"PASS smoke: {len(SAMPLE_SENTENCES)} sentences; model {result['model_version']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
