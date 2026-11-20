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


@lru_cache
def difficult_term_licenses(path=Path(__file__).with_name("difficult_terms.json")):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return value.get("licenses", {}) if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


_PARTICLES = tuple(sorted((
    "으로부터", "에게서", "한테서", "으로써", "으로서", "에게", "한테", "부터", "까지", "처럼", "보다",
    "마다", "조차", "마저", "밖에", "뿐", "으로", "에서", "에게", "께서", "은", "는", "이", "가",
    "을", "를", "의", "에", "와", "과", "도", "만", "로", "께", "야", "아",
), key=len, reverse=True))


@lru_cache(maxsize=4)
def _term_matcher(terms):
    alternatives = []
    particles = "|".join(map(re.escape, _PARTICLES))
    for term in sorted((term for term in set(terms) if term), key=lambda value: (-len(value), value)):
        if term.isascii() and term.isalpha() and len(term) <= 2 and term != term.upper():
            continue
        escaped = re.escape(term)
        if any("가" <= char <= "힣" for char in term):
            alternatives.append(r"(?<!\w)" + escaped + r"(?=(?:" + particles + r")?(?![가-힣]))")
        else:
            alternatives.append(r"(?<!\w)" + escaped + r"(?!\w)")
    return re.compile(r"(?=(?P<term>(?:" + "|".join(alternatives or [r"(?!)"]) + r")))")


def terms_in(text, dictionary=None):
    dictionary = difficult_terms() if dictionary is None else dictionary
    candidates = [(match.start("term"), match.end("term"), match.group("term"))
                  for match in _term_matcher(tuple(dictionary)).finditer(text)]
    selected = []
    for start, end, term in sorted(candidates, key=lambda item: (-(item[1] - item[0]), item[0])):
        if not any(start < right and end > left for left, right, _ in selected):
            selected.append((start, end, term))
    return [
        {"text": term, "start": len(text[:start].encode("utf-16-le")) // 2,
         "end": len(text[:end].encode("utf-16-le")) // 2,
         "easy": dictionary[term]["alternatives"], "source": ", ".join(dictionary[term]["sources"])}
        for start, end, term in sorted(selected)
    ]
