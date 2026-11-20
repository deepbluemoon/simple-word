"""NLI가 표시한 짝만 교사 LLM(gemma3:27b)으로 다시 판정한다. 두 판정이 모두 문제라고 한 짝만 제외 대상(exclude)으로 둔다.

    python -m training.nli_llm --nli data/nli.jsonl --pairs data/pairs.jsonl

data/nli.jsonl의 표시된 줄에 "llm": {"verdict": "same"|"contradiction"|"omission"|"addition", "reason": ...},
"exclude": true/false를 더해 다시 쓴다. training.nli.load_flags는 exclude가 있으면 그것을 쓴다.
"""
import argparse
import json
import os
import re
import urllib.request

OLLAMA = "http://localhost:11434/api/generate"
MODEL = "gemma3:27b"
VERDICTS = ("same", "contradiction", "omission", "addition")
PROMPT = """원문과, 원문을 쉬운 말로 바꾼 문장이 있습니다. 쉬운 말만 읽은 사람이 원문과 **다르게** 이해하게 되는 내용이 있는지 엄격하게 찾으세요.
찾을 것: 낱말을 틀린 뜻으로 풀어 쓴 것, 대상·조건·기간·부정이 바뀐 것, 원문의 핵심 정보가 빠진 것, 원문에 없는 사실을 넣은 것.
표현을 쉽게 바꾸거나 문장을 나눈 것은 문제가 아닙니다.

원문: {src}
쉬운 말: {tgt}

JSON 한 줄로: {{"differences": ["원문 표현 → 쉬운 말 표현: 무엇이 다른지", ...], "verdict": "same|contradiction|omission|addition"}}
다른 점이 하나도 없을 때만 same."""


def ask(src, tgt):
    body = json.dumps({"model": MODEL, "prompt": PROMPT.format(src=src, tgt=tgt), "stream": False, "format": "json",
                       "options": {"temperature": 0, "seed": 0, "num_predict": 400}}).encode()
    req = urllib.request.Request(OLLAMA, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        out = json.load(r)["response"]
    return parse(out)


def parse(out):
    try:
        d = json.loads(out)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", out, re.S)
        d = json.loads(m.group(0)) if m else {}
    verdict = str(d.get("verdict", "")).strip().lower()
    diffs = d.get("differences") or []
    reason = " / ".join(map(str, diffs)) if isinstance(diffs, list) else str(diffs)
    return {"verdict": verdict if verdict in VERDICTS else "unknown", "reason": (reason or str(d.get("reason", "")))[:500]}


def exclude(llm):
    """LLM도 문제(same이 아님)라고 했을 때만 뺀다. 답을 못 읽으면(unknown) 빼지 않는다."""
    return llm["verdict"] in ("contradiction", "omission", "addition")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--nli", default="data/nli.jsonl")
    ap.add_argument("--pairs", default="data/pairs.jsonl")
    a = ap.parse_args()
    pairs = {(p["doc_id"], p["idx"]): p for p in map(json.loads, open(a.pairs, encoding="utf-8"))}
    rows = [json.loads(l) for l in open(a.nli, encoding="utf-8")]
    done = 0
    for r in rows:
        if r.get("flag") and "llm" not in r:
            p = pairs[(r["doc_id"], r["idx"])]
            r["llm"] = {**ask(p["src"], p["tgt"]), "model": f"ollama:{MODEL}"}
            r["exclude"] = exclude(r["llm"])
            done += 1
            if done % 25 == 0:
                print(json.dumps({"judged": done}), flush=True)
    tmp = f"{a.nli}.tmp"  # 쓰다가 멈춰도 원래 판정 파일이 반쯤 지워지지 않게
    with open(tmp, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    os.replace(tmp, a.nli)
    flagged = [r for r in rows if r.get("flag")]
    print(json.dumps({"flagged": len(flagged), "judged": done, "exclude": sum(bool(r.get("exclude")) for r in flagged),
                      "verdicts": {v: sum(r.get("llm", {}).get("verdict") == v for r in flagged) for v in VERDICTS + ("unknown",)}}))
