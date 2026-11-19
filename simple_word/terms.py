"""보존 용어(법령·제도·기관명): 쉬운 말로 바꾸면 안 되는 말. 서빙(Simplifier 안전장치)과 학습(training.checks)이 같이 쓴다."""
import re
from functools import lru_cache
from pathlib import Path


@lru_cache
def preserve_terms(path=Path(__file__).with_name("preserve_terms.txt")):
    return tuple(l.strip() for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#"))


def found(term, text):
    """앞이 한글·영문에 붙어 있지 않은 곳에서 term 이 나오는가 (뒤에는 조사가 붙을 수 있음)."""
    return re.search(r"(?<![가-힣A-Za-z])" + re.escape(term), text) is not None


def missing_terms(src, out, terms):
    """원문에 있는 보존 용어 중 출력에서 빠진 것."""
    return [t for t in terms if found(t, src) and t not in out]
