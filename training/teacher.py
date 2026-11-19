"""sentences.jsonl → pairs.jsonl. 교사: Ollama gemma3:27b, temperature 0.2. 이미 만든 src는 건너뛴다.

`python -m training.teacher [--limit N] [--per-doc 8] [--recent-first]`
--per-doc N: 문서마다 최대 N문장만(문장 sha1 순으로 골라 결정적). 이미 만든 짝도 그 문서의 N에 센다.
--recent-first: docs.jsonl 게시일이 최근인 문서부터. 중간에 멈춰도 최근 글부터 쌓인다.
"""
import argparse, hashlib, json, re, urllib.request
from collections import defaultdict
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
    keep = [t for t in preserve if found(t, src)] + re.findall(r"[「『]([^「『」』]+)[」』]", src)
    if keep:
        extra += f"- 다음 용어·명칭은 바꾸지 말고 그대로 씁니다(필요하면 뒤에 괄호로 쉽게 풀이): {', '.join(keep)}\n"
    swaps = [f"{k} → {'/'.join(v['alternatives'])}" for k, v in nikl.items() if found(k, src)]
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


def plan(data_dir, done, per_doc=None, recent_first=False):
    """교사에게 보낼 문장 순서. per_doc이면 문서마다 sha1 순 앞 N개(이미 만든 짝 포함)만."""
    sents = [json.loads(l) for l in (Path(data_dir) / "sentences.jsonl").open(encoding="utf-8")]
    if per_doc:
        by_doc = defaultdict(list)
        for s in sents:
            by_doc[s["doc_id"]].append(s)
        keep = set()
        for rows in by_doc.values():
            made = [r for r in rows if r["text"] in done]
            rest = sorted((r for r in rows if r["text"] not in done), key=lambda r: hashlib.sha1(r["text"].encode()).hexdigest())
            keep.update(id(r) for r in rest[: max(per_doc - len(made), 0)])
        sents = [s for s in sents if id(s) in keep]
    if recent_first:
        pub = {d["id"]: d["published_at"] for d in map(json.loads, (Path(data_dir) / "docs.jsonl").open(encoding="utf-8"))}
        sents.sort(key=lambda s: (pub.get(s["doc_id"], ""), s["doc_id"], -s["idx"]), reverse=True)
    return sents


def run(data_dir="data", limit=None, gen=generate, log=print, per_doc=None, recent_first=False):
    data_dir = Path(data_dir)
    pairs_path = data_dir / "pairs.jsonl"
    done = {json.loads(l)["src"] for l in pairs_path.open(encoding="utf-8")} if pairs_path.exists() else set()
    preserve, nikl = preserve_terms(), nikl_dict(data_dir)
    n = 0
    with pairs_path.open("a", encoding="utf-8") as out:
        for s in plan(data_dir, done, per_doc, recent_first):
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
    ap.add_argument("--per-doc", type=int, help="문서마다 최대 문장 수")
    ap.add_argument("--recent-first", action="store_true", help="최근 문서부터")
    a = ap.parse_args()
    print("pairs", run(a.data, a.limit, per_doc=a.per_doc, recent_first=a.recent_first))
