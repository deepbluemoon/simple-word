"""숫자·단위·기준어를 정규화해 멀티셋으로 비교한다."""
import re
from collections import Counter

UNIT = {"조": 10**12, "억": 10**8, "천만": 10**7, "백만": 10**6, "만": 10**4, "천": 10**3}
NUM = re.compile(r"(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(조|억|천만|백만|만|천)?")
MEASURE = re.compile(r"\s*(개월|퍼센트|%|원|명|건|개|회|번|세|년|월|일|시|분|초|대|곳|장|차|배)")
DATE = re.compile(r"(?:(\d{4})년\s*)?(\d{1,2})월(?:\s*(\d{1,2})일)?")
PARTICLES = ("으로", "에서", "에게", "까지", "부터", "은", "는", "이", "가", "의", "에", "로", "을", "를", "도", "만")
CLAUSE = re.compile(r"[,;:!?。！？\n]")


def _fmt(v):
    return f"{v:.4f}".rstrip("0").rstrip(".")


def _anchor(text, start, dates):
    clause_start = max((m.end() for m in CLAUSE.finditer(text, 0, start)), default=0)
    prior_dates = [m for m in dates if clause_start <= m.end() <= start]
    if prior_dates:
        return "date:" + re.sub(r"\s+", "", prior_dates[-1].group())
    prefix = text[clause_start:start].rstrip()
    word = re.search(r"[가-힣A-Za-z][가-힣A-Za-z0-9]*$", prefix)
    if not word:
        return ""
    value = word.group()
    for particle in PARTICLES:
        if value.endswith(particle) and len(value) > len(particle):
            value = value[:-len(particle)]
            break
    return value


def numbers(s):
    """Counter of (normalized value, unit, nearest preceding date/noun).

    '100분의 20'·'20%'·'20퍼센트' and compound amounts keep their old
    normalization; repeated equal values remain distinct counter entries.
    """
    s = re.sub(r"[’‘'](\d{2})(?![\d.])", r"20\1", s)  # ’26 = 2026
    s = re.sub(r"(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.?", r"\1년 \2월 \3일", s)
    s = re.sub(r"(?<![\d.])(\d{1,2})\.(\d{1,2})(?=\.|\s*~)|(?<=~)\s*(\d{1,2})\.(\d{1,2})(?![\d.])",
               lambda m: f"{m[1] or m[3]}월 {m[2] or m[4]}일", s)
    s = re.sub(r"(\d{4})\s*[/~–-]\s*(\d{4})년", r"\1년 \2년", s)
    s = re.sub(r"(\d+(?:\.\d+)?)\s*분의\s*(\d+(?:\.\d+)?)",
               lambda m: _fmt(float(m[2]) / float(m[1]) * 100) + "%", s)

    dates = list(DATE.finditer(s))
    found, cur, cur_unit, cur_start, cur_end = [], None, 0, 0, 0
    for m in NUM.finditer(s):
        value = float(m[1].replace(",", "") + (m[2] or "")) * UNIT.get(m[3], 1)
        scale = UNIT.get(m[3], 1)
        if cur is not None and 1 < cur_unit and scale < cur_unit and not s[cur_end:m.start()].strip():
            cur += value
            cur_unit, cur_end = scale, m.end()
            continue
        if cur is not None:
            found.append((cur, cur_start, cur_end))
        cur, cur_unit, cur_start, cur_end = value, scale, m.start(), m.end()
    if cur is not None:
        found.append((cur, cur_start, cur_end))

    occurrences = []
    for value, start, end in found:
        measure = MEASURE.match(s, end)
        unit = measure.group(1) if measure else ""
        if unit == "퍼센트":
            unit = "%"
        occurrences.append((_fmt(value), unit, start))

    counts = Counter(unit for _, unit, _ in occurrences)
    pairs = Counter()
    for value, unit, start in occurrences:
        anchor = _anchor(s, start, dates) if counts[unit] > 1 and unit not in {"년", "월", "일", "시", "분", "초"} else ""
        pairs[(value, unit, anchor)] += 1
    return pairs
