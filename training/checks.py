"""교사 짝 자동 검사(규칙을 바꾼 뒤 `python -m training.checks` 로 pairs.jsonl 다시 검사): 숫자·날짜·금액·비율 일치, 보존 용어 유지, 대상·기한·조건 누락, 영어 단어 보존/사전 대체, 길이·한 문단(쉬운 말은 짧아야 하고 한 문장은 한 문장으로)."""
import re

from simple_word.numbers import numbers  # noqa: F401  (서빙과 같은 함수)
from simple_word.terms import found, missing_terms

ENGLISH = re.compile(r"[A-Za-z][A-Za-z0-9&+\-]*[A-Za-z0-9]")


def target_nouns(s):
    return [re.sub(r"(?:을|를)$", "", w) for w in re.findall(r"(\S+?(?:을|를))\s*대상으로", s)]


DEADLINE_SRC = re.compile(r"까지|이내|기한|마감")
DEADLINE_TGT = re.compile(r"까지|이내|안에|안으로|기한|마감|전에|전까지")
COND_SRC = re.compile(r"경우|조건|한하여|한해서|(?<![가-힣])단,")  # '공단,' 같은 기관명 끝은 제외
COND_TGT = re.compile(r"경우|때|면|조건|만|한해|한하여|(?<![가-힣])단,")
MAX_LEN_RATIO = 1.3  # 교사 출력이 원문보다 이만큼 넘게 길면 탈락 (이슈 #28)


def check_pair(src, tgt, preserve, nikl):
    c = {}
    ns, nt = numbers(src), numbers(tgt)
    missing, added = ns - nt, nt - ns
    c["numbers"] = {
        "ok": not missing and not added,
        "missing": sorted(f"{value} {unit} ({anchor})".strip() for (value, unit, anchor), n in missing.items() for _ in range(n)),
        "added": sorted(f"{value} {unit} ({anchor})".strip() for (value, unit, anchor), n in added.items() for _ in range(n)),
    }
    names = re.findall(r"[「『]([^「『」』]+)[」』]", src)  # 「」 안 법령·사업명도 그대로
    c["preserve"] = {"ok": not (m := missing_terms(src, tgt, preserve) + [t for t in names if t not in tgt]), "missing": m}
    miss = [f"대상:{n}" for n in target_nouns(src) if n not in tgt]
    if DEADLINE_SRC.search(src) and not DEADLINE_TGT.search(tgt):
        miss.append("기한")
    if COND_SRC.search(src) and not COND_TGT.search(tgt):
        miss.append("조건")
    c["conditions"] = {"ok": not miss, "missing": miss}
    eng = [w for w in dict.fromkeys(ENGLISH.findall(src))
           if w.lower() not in tgt.lower() and not any(a in tgt for a in nikl.get(w, {}).get("alternatives", []))]
    c["english"] = {"ok": not eng, "missing": eng}
    ratio = round(len(tgt) / len(src), 3)
    c["length"] = {"ok": ratio <= MAX_LEN_RATIO, "ratio": ratio}
    c["multiline"] = {"ok": "\n" not in tgt.strip()}
    fails = [k for k, v in c.items() if not v["ok"]]
    return {"checks": c, "passed": not fails, "reject_reason": ",".join(fails) or None}


def recheck(data_dir="data"):
    """pairs.jsonl 전체를 지금 규칙으로 다시 검사해 덮어쓴다. (통과 수, 탈락 이유별 수)를 돌려준다."""
    import collections, json
    from pathlib import Path
    from training.terms import nikl_dict, preserve_terms

    data = Path(data_dir)
    preserve, nikl = preserve_terms(), nikl_dict(data)
    pairs = [json.loads(l) for l in (data / "pairs.jsonl").open(encoding="utf-8")]
    for p in pairs:
        if p["tgt"]:
            p.update(check_pair(p["src"], p["tgt"], preserve, nikl))
    (data / "pairs.jsonl").write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in pairs), encoding="utf-8")
    reasons = collections.Counter(r for p in pairs for r in (p.get("reject_reason") or "").split(",") if r)
    return sum(p["passed"] for p in pairs), len(pairs), dict(reasons)


if __name__ == "__main__":
    import sys

    passed, total, reasons = recheck(sys.argv[1] if len(sys.argv) > 1 else "data")
    print("passed", passed, "/", total)
    print(reasons)
