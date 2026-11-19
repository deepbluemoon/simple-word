"""교사 짝 자동 검사: 숫자·날짜·금액·비율 일치, 보존 용어 유지, 대상·기한·조건 누락, 영어 단어 보존/사전 대체."""
import re

from training.terms import found

UNIT = {"조": 10**12, "억": 10**8, "천만": 10**7, "백만": 10**6, "만": 10**4, "천": 10**3}
NUM = re.compile(r"(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(조|억|천만|백만|만|천)?")
ENGLISH = re.compile(r"[A-Za-z][A-Za-z0-9&+\-]*[A-Za-z0-9]")


def _fmt(v):
    return f"{v:.4f}".rstrip("0").rstrip(".")


def numbers(s):
    """값의 집합. '100분의 20'·'20%'·'20퍼센트' → 20, '3억 5,000만' → 350000000, 날짜는 숫자별로."""
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


def target_nouns(s):
    return [re.sub(r"(?:을|를)$", "", w) for w in re.findall(r"(\S+?(?:을|를))\s*대상으로", s)]


DEADLINE_SRC = re.compile(r"까지|이내|기한|마감")
DEADLINE_TGT = re.compile(r"까지|이내|안에|안으로|기한|마감|전에|전까지")
COND_SRC = re.compile(r"경우|조건|한하여|한해|단,")
COND_TGT = re.compile(r"경우|때|면|조건|만|한해|한하여|단,")


def check_pair(src, tgt, preserve, nikl):
    c = {}
    ns, nt = numbers(src), numbers(tgt)
    c["numbers"] = {"ok": ns == nt, "missing": sorted(ns - nt), "added": sorted(nt - ns)}
    keep = [t for t in preserve if found(t, src)] + re.findall(r"[「『]([^」』]+)[」』]", src)
    c["preserve"] = {"ok": not (m := [t for t in keep if t not in tgt]), "missing": m}
    miss = [f"대상:{n}" for n in target_nouns(src) if n not in tgt]
    if DEADLINE_SRC.search(src) and not DEADLINE_TGT.search(tgt):
        miss.append("기한")
    if COND_SRC.search(src) and not COND_TGT.search(tgt):
        miss.append("조건")
    c["conditions"] = {"ok": not miss, "missing": miss}
    eng = [w for w in dict.fromkeys(ENGLISH.findall(src))
           if w.lower() not in tgt.lower() and not any(a in tgt for a in nikl.get(w, []))]
    c["english"] = {"ok": not eng, "missing": eng}
    fails = [k for k, v in c.items() if not v["ok"]]
    return {"checks": c, "passed": not fails, "reject_reason": ",".join(fails) or None}
