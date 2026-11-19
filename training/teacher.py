"""sentences.jsonl → pairs.jsonl. 교사: Ollama gemma3:27b, temperature 0.2. 이미 만든 src는 건너뛴다.

`python -m training.teacher [--limit N]`
"""
import argparse, json, re, urllib.request
from pathlib import Path

from training import checks
from training.terms import found, nikl_dict, preserve_terms

MODEL = "gemma3:27b"
OLLAMA = "http://localhost:11434/api/generate"
ENGLISH = re.compile(r"[A-Za-z][A-Za-z0-9&+\-]*[A-Za-z0-9]")

PROMPT = """다음 공문서 문장을 초등학생도 이해할 수 있는 쉬운 한국어로 바꿔 주세요.
규칙:
- 어려운 한자어·행정 용어는 쉬운 말로 풀고, 문장은 짧게 씁니다.
- 숫자·날짜·금액·비율은 원문과 같은 값으로 씁니다(예: "100분의 20"은 "20%"로 써도 됩니다). 원문에 없는 숫자는 쓰지 않습니다.
- 대상(누가), 기한(언제까지), 조건(어떤 경우에)은 하나도 빠뜨리지 않습니다.
- 뜻을 바꾸지 않습니다. 의무("해야 합니다")를 가능("할 수 있습니다")으로 바꾸지 않습니다.
{extra}- 설명이나 머리말 없이 바꾼 문장만 출력합니다.
원문: {src}
쉬운 말:"""


def build_prompt(src, preserve, nikl):
    extra = ""
    keep = [t for t in preserve if found(t, src)] + re.findall(r"[「『]([^」』]+)[」』]", src)
    if keep:
        extra += f"- 다음 용어·명칭은 바꾸지 말고 그대로 씁니다(필요하면 뒤에 괄호로 쉽게 풀이): {', '.join(keep)}\n"
    swaps = [f"{k} → {'/'.join(v)}" for k, v in nikl.items() if len(k) >= 2 and found(k, src)]
    if swaps:
        extra += f"- 다음 외래어는 쉬운 우리말로 바꿉니다: {'; '.join(swaps)}\n"
    eng = list(dict.fromkeys(ENGLISH.findall(src)))
    if eng:
        extra += f"- 영어 단어·약어는 그대로 씁니다: {', '.join(eng)}\n"
    return PROMPT.format(src=src, extra=extra)


def generate(prompt):
    body = json.dumps({"model": MODEL, "prompt": prompt, "stream": False,
                       "options": {"temperature": 0.2, "seed": 0, "num_predict": 400}}).encode()
    req = urllib.request.Request(OLLAMA, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:  # Ollama가 꺼져 있으면 여기서 멈춘다(짝을 버리지 않음)
        out = json.load(r)["response"]
    return re.sub(r"^\s*쉬운 말\s*[:：]\s*", "", out).strip().strip('"“”')


def run(data_dir="data", limit=None, gen=generate, log=print):
    data_dir = Path(data_dir)
    pairs_path = data_dir / "pairs.jsonl"
    done = {json.loads(l)["src"] for l in pairs_path.open(encoding="utf-8")} if pairs_path.exists() else set()
    preserve, nikl = preserve_terms(), nikl_dict(data_dir)
    n = 0
    with pairs_path.open("a", encoding="utf-8") as out:
        for line in (data_dir / "sentences.jsonl").open(encoding="utf-8"):
            s = json.loads(line)
            if s["text"] in done or (limit is not None and n >= limit):
                continue
            tgt = gen(build_prompt(s["text"], preserve, nikl))
            if tgt:
                result = checks.check_pair(s["text"], tgt, preserve, nikl)
            else:  # 교사 출력 없음 → 짝 버림(이유 기록)
                result = {"checks": {}, "passed": False, "reject_reason": "teacher_empty"}
            pair = {"doc_id": s["doc_id"], "idx": s["idx"], "src": s["text"], "tgt": tgt, "teacher": f"ollama:{MODEL}", **result}
            out.write(json.dumps(pair, ensure_ascii=False) + "\n")
            out.flush()
            done.add(s["text"])
            n += 1
            log(f"{'PASS' if pair['passed'] else 'FAIL ' + pair['reject_reason']}: {tgt[:60]}")
    return n


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    print("pairs", run(a.data, a.limit))
