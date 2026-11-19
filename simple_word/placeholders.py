"""숫자·날짜·금액과 보존 용어를 모델 입력 전에 자리표시자로 바꾸고, 출력에서 되돌린다 (v3, 이슈 fallback 줄이기).

    masked, slots = mask("지원금 3억 5,000만 원을 기초연금 수급자에게 ‘26.6.25까지")
    # masked = "지원금 <N0> 원을 <T0> 수급자에게 <N1>까지", slots = {"<N0>": "3억 5,000만", "<T0>": "기초연금", "<N1>": "‘26.6.25"}
    unmask("<T0> 받는 분께 <N1>까지 <N0> 원", slots)  # → 원래 글자로. 자리표시자가 빠지거나 모르는 것이 있으면 None

모델은 숫자를 직접 쓰지 않으므로 숫자를 틀릴 수 없다. 자리표시자를 빠뜨리면 원문으로 돌린다(fallback).
학습 짝에도 같은 변환을 한다(mask_pair): 교사 출력에서 원문 조각을 그대로 찾아 자리표시자로 바꾼다.
"""
import re

from simple_word.terms import found, preserve_terms

MAX_N, MAX_T = 20, 10
NUM_TOKENS = [f"<N{i}>" for i in range(MAX_N)]
TERM_TOKENS = [f"<T{i}>" for i in range(MAX_T)]
TOKENS = NUM_TOKENS + TERM_TOKENS
_UNIT = r"(?:조|억|천만|백만|만|천)"
_NUM = r"\d(?:[\d,]*\d)?(?:\.\d+)*"  # 1,000 / 3.5 / 11.18 / 2026.11.19
NUM_SPAN = re.compile(rf"[’‘']?{_NUM}(?:\s?{_UNIT}(?:\s?{_NUM}\s?{_UNIT}?)*)?(?:\s?%|퍼센트)?")
NAME = re.compile(r"[「『][^「『」』]+[」』]")
SLOT = re.compile(r"<[NT]\d+>")


def _spans(text, terms):
    """[(start, end, kind)] 겹치지 않게. 「」 이름 → 보존 용어(긴 것부터) → 숫자."""
    taken, out = [False] * len(text), []

    def add(a, b, kind):
        if b > a and not any(taken[a:b]):
            taken[a:b] = [True] * (b - a)
            out.append((a, b, kind))

    for m in NAME.finditer(text):
        add(m.start(), m.end(), "T")
    for t in sorted(terms, key=len, reverse=True):
        for m in re.finditer(r"(?<![가-힣A-Za-z])" + re.escape(t), text):
            add(m.start(), m.end(), "T")
    for m in NUM_SPAN.finditer(text):
        add(m.start(), m.end(), "N")
    return sorted(out)


def mask(text, terms=None):
    """→ (자리표시자로 바꾼 글, {자리표시자: 원래 글자}). 같은 글자는 같은 자리표시자. 자리가 모자라면 남은 것은 그대로 둔다."""
    terms = preserve_terms() if terms is None else terms
    terms = [t for t in terms if found(t, text)]
    slots, by_text, n, k = {}, {}, 0, 0
    pieces, last = [], 0
    for a, b, kind in _spans(text, terms):
        frag = text[a:b]
        tok = by_text.get(frag)
        if tok is None:
            if kind == "N" and n < MAX_N:
                tok, n = f"<N{n}>", n + 1
            elif kind == "T" and k < MAX_T:
                tok, k = f"<T{k}>", k + 1
            else:
                continue
            by_text[frag], slots[tok] = tok, frag
        pieces += [text[last:a], tok]
        last = b
    pieces.append(text[last:])
    return "".join(pieces), slots


def unmask(text, slots):
    """자리표시자를 원래 글자로. 원문의 자리표시자가 하나라도 빠지거나, 원문에 없는 자리표시자가 나오면 None."""
    used = SLOT.findall(text)
    if set(used) != set(slots):
        return None
    out = SLOT.sub(lambda m: slots[m.group(0)], text)
    return re.sub(r"\s+", " ", out).strip()


def mask_pair(src, tgt, terms=None):
    """학습 짝 변환. 원문 조각이 교사 출력에 글자 그대로 없으면 None(그 짝은 자리표시자 학습에 못 씀)."""
    if SLOT.search(src) or SLOT.search(tgt):
        return None
    masked_src, slots = mask(src, terms)
    if not slots:
        return masked_src, tgt
    back = {frag: tok for tok, frag in slots.items()}
    alts = []
    for frag in sorted(back, key=len, reverse=True):  # 한 번에 바꿔야 이미 넣은 <N0>의 0을 다시 바꾸지 않는다
        edge = (r"(?<![\d,.])", r"(?![\d,])") if back[frag].startswith("<N") else ("", "")
        alts.append(edge[0] + re.escape(frag) + edge[1])
    out = re.sub("|".join(alts), lambda m: back[m.group(0)], tgt)
    if set(SLOT.findall(out)) != set(slots):  # 원문 조각이 교사 출력에 글자 그대로 없음
        return None
    if re.search(r"\d", SLOT.sub("", out)):  # 자리표시자로 못 바꾼 숫자가 남음(교사가 숫자 모양을 바꿈)
        return None
    return masked_src, out
