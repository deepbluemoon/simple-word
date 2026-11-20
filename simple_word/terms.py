"""보존 용어(법령·제도·기관명): 쉬운 말로 바꾸면 안 되는 말. 서빙(Simplifier 안전장치)과 학습(training.checks)이 같이 쓴다."""
import json
import re
from functools import lru_cache
from pathlib import Path


@lru_cache
def preserve_terms(path=Path(__file__).with_name("preserve_terms.txt")):
    return tuple(l.strip() for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#"))


def found(term, text):
    """앞이 한글·영문에 붙어 있지 않은 곳에서 term 이 나오는가 (뒤에는 조사가 붙을 수 있음)."""
    return term in text and re.search(r"(?<![가-힣A-Za-z])" + re.escape(term), text) is not None


def missing_terms(src, out, terms):
    """원문에 있는 보존 용어 중 출력에서 빠진 것."""
    return [t for t in terms if found(t, src) and t not in out]


@lru_cache
def difficult_terms(path=Path(__file__).with_name("difficult_terms.json")):
    """Load the static runtime dictionary without importing training code."""
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return value.get("terms", {}) if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def terms_in(text, dictionary=None):
    result = []
    for term, entry in (dictionary if dictionary is not None else difficult_terms()).items():
        if not found(term, text):
            continue
        offset = 0
        while (start := text.find(term, offset)) >= 0:
            offset = start + 1
            boundary = text[max(0, start - 1):start + len(term)]
            if found(term, boundary):
                utf16_start = len(text[:start].encode("utf-16-le")) // 2
                result.append({
                    "text": term, "start": utf16_start,
                    "end": utf16_start + len(term.encode("utf-16-le")) // 2,
                    "easy": entry["alternatives"], "source": ", ".join(entry["sources"]),
                })
    return sorted(result, key=lambda item: (item["start"], item["end"]))
