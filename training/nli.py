"""학습 짝 뜻 검사: 원문(src)과 쉬운 말(tgt)이 같은 뜻인지 NLI 모델로 판정해 data/nli.jsonl에 적는다(pairs.jsonl은 그대로).

    python -m training.nli --pairs data/pairs.jsonl --out data/nli.jsonl
    python -m training.train ... --nli data/nli.jsonl   # flag가 있는 짝을 학습에서 뺀다

모델: MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7 (MIT, 한국어 포함 다국어 NLI). 두 방향으로 본다.
- 정방향 src → tgt: 원문이 쉬운 말을 뒷받침하는가. 모순 확률이 높으면 뜻이 바뀐 것(contradiction).
- 역방향 tgt → src: 쉬운 말만으로 원문 내용이 나오는가. 함의 확률이 아주 낮으면 원문 정보가 빠진 것(omission).
쉬운 말은 원래 세부를 줄이므로 omission 기준은 느슨하게(아주 낮을 때만) 둔다. 임계값은 docs/NLI_FILTER.md.
"""
import argparse
import json
from pathlib import Path

MODEL = "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7"
CONTRADICTION = 0.9  # 정방향 또는 역방향 모순 확률이 이보다 크면 뜻이 바뀐 짝(0.5는 표현만 바꾼 짝도 많이 걸림)
OMISSION = 0.05  # 역방향 함의 확률이 이보다 작고 정방향 함의도 0.5 미만이면 정보 누락 짝


def flag(r, contradiction=CONTRADICTION, omission=OMISSION):
    """판정 한 줄 → 걸러낼 이유(None이면 통과)."""
    if max(r["fwd"]["contradiction"], r["bwd"]["contradiction"]) > contradiction:
        return "contradiction"
    if r["bwd"]["entailment"] < omission and r["fwd"]["entailment"] < 0.5:
        return "omission"
    return None


def load_flags(path):
    """data/nli.jsonl → 걸러낼 짝의 (doc_id, idx) 집합."""
    return {(r["doc_id"], r["idx"]) for r in map(json.loads, open(path, encoding="utf-8")) if r.get("flag")}


def judge(pairs, batch=32, device=None):
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    device = device or ("mps" if torch.backends.mps.is_available() else "cpu")
    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL).to(device).eval()
    labels = [model.config.id2label[i].lower() for i in range(model.config.num_labels)]

    def probs(premises, hyps):
        enc = tok(premises, hyps, truncation=True, max_length=256, padding=True, return_tensors="pt").to(device)
        with torch.no_grad():
            p = model(**enc).logits.float().softmax(-1).cpu().tolist()
        return [{k: round(v, 4) for k, v in zip(labels, row)} for row in p]

    for i in range(0, len(pairs), batch):
        part = pairs[i:i + batch]
        src, tgt = [p["src"] for p in part], [p["tgt"] for p in part]
        for p, f, b in zip(part, probs(src, tgt), probs(tgt, src)):
            r = {"doc_id": p["doc_id"], "idx": p["idx"], "fwd": f, "bwd": b, "model": MODEL}
            r["flag"] = flag(r)
            yield r


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default="data/pairs.jsonl")
    ap.add_argument("--out", default="data/nli.jsonl")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    pairs = [p for p in map(json.loads, open(a.pairs, encoding="utf-8")) if p.get("passed") and p.get("tgt")]
    pairs = pairs[:a.limit] if a.limit else pairs
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    n = flagged = 0
    with open(a.out, "w", encoding="utf-8") as f:
        for r in judge(pairs):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            n, flagged = n + 1, flagged + bool(r["flag"])
    print(json.dumps({"pairs": n, "flagged": flagged}))
