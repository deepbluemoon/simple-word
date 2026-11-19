"""숫자·날짜·금액·비율 정규화. 서빙(Simplifier 숫자 안전장치)과 학습(교사 짝 검사·평가)이 같이 쓴다."""
import re

UNIT = {"조": 10**12, "억": 10**8, "천만": 10**7, "백만": 10**6, "만": 10**4, "천": 10**3}
NUM = re.compile(r"(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(조|억|천만|백만|만|천)?")


def _fmt(v):
    return f"{v:.4f}".rstrip("0").rstrip(".")


def numbers(s):
    """값의 집합. '100분의 20'·'20%'·'20퍼센트' → 20, '3억 5,000만' → 350000000, 날짜는 숫자별로."""
    s = re.sub(r"[’‘'](\d{2})(?![\d.])", r"20\1", s)  # ’26 = 2026
    s = re.sub(r"(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.?", r"\1년 \2월 \3일", s)
    s = re.sub(r"(?<![\d.])(\d{1,2})\.(\d{1,2})(?=\.|\s*~)|(?<=~)\s*(\d{1,2})\.(\d{1,2})(?![\d.])",
               lambda m: f"{m[1] or m[3]}월 {m[2] or m[4]}일", s)  # 11.18. / 3.15~4.5 는 날짜, 3.6 은 소수
    s = re.sub(r"(\d+(?:\.\d+)?)\s*분의\s*(\d+(?:\.\d+)?)", lambda m: _fmt(float(m[2]) / float(m[1]) * 100) + "%", s)
    vals, cur, cur_unit, cur_end = [], None, 0, -1
    for m in NUM.finditer(s):
        v = float(m[1].replace(",", "") + (m[2] or ""))
        unit = UNIT.get(m[3], 1)
        v *= unit
        if cur is not None and 1 < cur_unit and unit < cur_unit and not s[cur_end : m.start()].strip():
            cur, cur_unit = cur + v, unit  # 3억 5,000만 원 처럼 이어진 단위
        else:
            if cur is not None:
                vals.append(cur)
            cur, cur_unit = v, unit
        cur_end = m.end()
    if cur is not None:
        vals.append(cur)
    return {_fmt(v) for v in vals}
