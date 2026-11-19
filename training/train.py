"""pairs.jsonl(passed=true) → data/v<N>/{train,valid,test}.jsonl(문서 단위 분할) → KoBART 전체 파인튜닝(MPS).

`python -m training.train --version v1 [--pairs data/pairs.jsonl] [--epochs 3]`
결과: models/<version>/hf/ (HF 체크포인트, export.py 입력) + train_metrics.json
"""
import argparse, hashlib, json, random, re, time
from pathlib import Path

from training.export import PARITY_INPUTS

BASE = "gogamza/kobart-base-v2"
EOS = 1  # KoBART: bos = eos = decoder_start = 1
SEED = 0


def split_of(doc_id):
    """문서 id 해시로 고정 분할(8:1:1). 같은 문서의 문장은 항상 같은 쪽."""
    b = int(hashlib.sha1(doc_id.encode()).hexdigest(), 16) % 10
    return "test" if b == 0 else "valid" if b == 1 else "train"


def time_split_of(rows, published):
    """시간순 분할: 게시일 순으로 문서를 늘어놓고 앞 80% train, 다음 10% valid, 마지막 10% test (게시일 없는 문서는 가장 오래된 쪽)."""
    docs = sorted({r["doc_id"] for r in rows}, key=lambda d: (published.get(d, ""), d))
    n = len(docs)
    return {d: "train" if i < round(n * 0.8) else "valid" if i < round(n * 0.9) else "test" for i, d in enumerate(docs)}


def _near(s):
    return re.sub(r"[^가-힣]", "", s)


def leakage(splits, eval_texts=()):
    """valid/test, 고정 parity 입력, 사람 검수 평가셋(eval_texts)이 train과 겹치는 건수. 모두 0이어야 한다."""
    train = splits["train"]
    docs, exact, near = {r["doc_id"] for r in train}, {r["src"] for r in train}, {_near(r["src"]) for r in train}
    held = splits["valid"] + splits["test"]
    return {"doc_overlap": sum(r["doc_id"] in docs for r in held), "src_exact_overlap": sum(r["src"] in exact for r in held),
            "src_near_overlap": sum(_near(r["src"]) in near for r in held),
            "parity_overlap": sum(p in exact or _near(p) in near for p in PARITY_INPUTS),
            "eval_set_overlap": sum(t in exact or _near(t) in near for t in eval_texts)}


def stop_epoch(valid_losses, patience=2):
    """early stopping: valid 손실이 patience 번 연속 최저를 못 넘으면 멈춘다. (멈출지, 가장 좋은 epoch 번호 1부터)"""
    best = min(range(len(valid_losses)), key=valid_losses.__getitem__)
    return len(valid_losses) - 1 - best >= patience, best + 1


def make_splits(pairs_paths, out_dir, by="hash", published=None):
    rows = []
    for path in pairs_paths:
        for line in Path(path).open(encoding="utf-8"):
            p = json.loads(line)
            if p.get("passed") and p.get("tgt"):
                rows.append({"doc_id": p["doc_id"], "src": p["src"], "tgt": p["tgt"]})
    owner = time_split_of(rows, published or {}) if by == "time" else {r["doc_id"]: split_of(r["doc_id"]) for r in rows}
    splits = {"train": [], "valid": [], "test": []}
    for r in rows:
        splits[owner[r["doc_id"]]].append(r)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in splits.items():
        (out_dir / f"{name}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return splits


def encode(tok, rows, max_len=256):
    ids = lambda s: tok(s, add_special_tokens=False)["input_ids"][: max_len - 1] + [EOS]
    return [(ids(r["src"]), ids(r["tgt"])) for r in rows]


def batches(data, size, tok, torch, shuffle_rng=None):
    order = list(range(len(data)))
    if shuffle_rng:
        shuffle_rng.shuffle(order)
    pad = tok.pad_token_id
    for i in range(0, len(order), size):
        chunk = [data[j] for j in order[i : i + size]]
        L, T = max(len(s) for s, _ in chunk), max(len(t) for _, t in chunk)
        x = torch.tensor([s + [pad] * (L - len(s)) for s, _ in chunk])
        y = torch.tensor([t + [-100] * (T - len(t)) for _, t in chunk])
        yield x, (x != pad).long(), y


def placeholder_rows(rows):
    """짝을 자리표시자 형태로 (simple_word.placeholders). 교사가 숫자 모양을 바꿔 못 바꾸는 짝은 뺀다. → (rows, 뺀 수)"""
    from simple_word.placeholders import mask_pair

    out = []
    for r in rows:
        m = mask_pair(r["src"], r["tgt"])
        if m:
            out.append({**r, "src": m[0], "tgt": m[1]})
    return out, len(rows) - len(out)


def add_placeholder_tokens(tok):
    """<N0>..<T9>를 일반 추가 토큰으로 넣고, 추가 토큰 뒤에 '▁'를 붙이지 않게 한다(<N0>원 ↔ <N0> 원 구별).
    추가 토큰이 없는 글의 토큰화는 그대로다."""
    from tokenizers import pre_tokenizers
    from simple_word.placeholders import TOKENS

    tok.add_tokens(TOKENS)
    tok.backend_tokenizer.pre_tokenizer = pre_tokenizers.Metaspace(replacement="\u2581", prepend_scheme="first", split=True)
    return tok


def init_placeholder_embeddings(tok, model):
    """새 토큰이 서로 비슷하게 시작하면 모델이 모두 <N0>으로 쓴다(v3-dry 첫 시도: fallback 43%).
    <Nk>는 숫자 k 토큰('▁k', 10~19는 '▁10'…) 임베딩으로, <Tk>는 숫자 k와 '▁명칭'의 평균으로 시작해 서로 구별되게 한다.
    마스킹 뒤 원문에는 숫자가 남지 않으므로 <Nk>와 진짜 숫자가 헷갈릴 일이 없다. KoBART는 입력·출력 임베딩을 공유한다."""
    import torch
    from simple_word.placeholders import MAX_N, MAX_T

    emb = model.get_input_embeddings().weight
    vid = lambda t: tok.convert_tokens_to_ids(t)
    name = emb[vid("▁명칭")]
    with torch.no_grad():
        for k in range(MAX_N):
            emb[vid(f"<N{k}>")] = emb[vid(f"▁{k}")]
        for k in range(MAX_T):
            emb[vid(f"<T{k}>")] = (emb[vid(f"▁{k}")] + name) / 2


def train(version, pairs_paths, epochs=8, lr=5e-5, batch=8, data_root="data", model_root="models", split="hash", docs=None,
          eval_set=None, patience=2, placeholders=False):
    published = {}
    if docs:
        published = {d["id"]: d["published_at"] for d in map(json.loads, Path(docs).open(encoding="utf-8"))}
    snapshot = Path(data_root) / version
    splits = make_splits(pairs_paths, snapshot, split, published)
    if not splits["train"]:
        raise ValueError(f"train 분할이 비었다: passed=true 짝이 없음 ({pairs_paths})")
    eval_texts = [json.loads(l)["src"] for l in Path(eval_set).open(encoding="utf-8")] if eval_set else []
    leaks = leakage(splits, eval_texts)
    if any(v for k, v in leaks.items() if k != "parity_overlap"):
        raise ValueError(f"train과 valid/test가 겹친다: {leaks}")

    import torch
    from transformers import AutoTokenizer, BartForConditionalGeneration

    random.seed(SEED)
    torch.manual_seed(SEED)
    torch.use_deterministic_algorithms(True, warn_only=True)
    tok = AutoTokenizer.from_pretrained(BASE)
    model = BartForConditionalGeneration.from_pretrained(BASE)
    fit = {"train": splits["train"], "valid": splits["valid"]}  # test는 원문 그대로 둔다(평가는 서빙 경로가 자리표시자를 처리)
    ph_info = None
    if placeholders:
        add_placeholder_tokens(tok)
        model.resize_token_embeddings(len(tok))
        init_placeholder_embeddings(tok, model)
        (fit["train"], d_train), (fit["valid"], d_valid) = placeholder_rows(fit["train"]), placeholder_rows(fit["valid"])
        ph_info = {"dropped_train": d_train, "dropped_valid": d_valid, "vocab": len(tok)}
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model.to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=lr)
    train_data, valid_data = encode(tok, fit["train"]), encode(tok, fit["valid"])
    rng, history, t0, best_epoch = random.Random(SEED), [], time.time(), epochs
    for epoch in range(epochs):
        model.train()
        for x, m, y in batches(train_data, batch, tok, torch, rng):
            loss = model(input_ids=x.to(device), attention_mask=m.to(device), labels=y.to(device)).loss
            loss.backward()
            opt.step()
            opt.zero_grad()
        model.eval()
        with torch.no_grad():
            vl = [model(input_ids=x.to(device), attention_mask=m.to(device), labels=y.to(device)).loss.item()
                  for x, m, y in batches(valid_data, batch, tok, torch)]
        history.append({"epoch": epoch + 1, "train_last_loss": round(loss.item(), 4), "valid_loss": round(sum(vl) / len(vl), 4) if vl else None})
        print(history[-1], flush=True)
        if not vl:
            continue
        stop, best_epoch = stop_epoch([h["valid_loss"] for h in history], patience)
        if best_epoch == epoch + 1:  # 가장 좋은 epoch 가중치를 CPU에 보관
            best_state = {k: v.detach().to("cpu", copy=True) for k, v in model.state_dict().items()}
        if stop:
            break
    if valid_data:
        model.load_state_dict(best_state)
    out = Path(model_root) / version / "hf"
    model.save_pretrained(out)
    tok.save_pretrained(out)
    metrics = {"base_model": BASE, "data_snapshot": str(snapshot), "device": device, "seed": SEED, "epochs": epochs,
               "lr": lr, "batch": batch, "train_seconds": round(time.time() - t0, 1),
               "best_epoch": best_epoch, "patience": patience, "split": split, "sizes": {k: len(v) for k, v in splits.items()}, "leakage": leaks, "history": history,
               "placeholders": ph_info, "eval_set": str(eval_set) if eval_set else None}
    (out / "train_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=1), encoding="utf-8")
    return metrics


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--pairs", nargs="+", default=["data/pairs.jsonl"])
    ap.add_argument("--epochs", type=int, default=8, help="최대 epoch (early stopping)")
    ap.add_argument("--lr", type=float, default=5e-5)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--split", choices=["hash", "time"], default="hash")
    ap.add_argument("--docs", help="게시일을 읽을 docs.jsonl (--split time 에 필요)")
    ap.add_argument("--eval-set", help="사람 검수 평가셋 jsonl(src 필드) — train과 겹치면 학습 거부")
    ap.add_argument("--check-leakage", action="store_true", help="학습하지 않고 분할·누수 건수만 출력")
    ap.add_argument("--placeholders", action="store_true", help="숫자·보존 용어를 자리표시자로 바꿔 학습(v3)")
    a = ap.parse_args()
    if a.check_leakage:
        pub = {d["id"]: d["published_at"] for d in map(json.loads, open(a.docs, encoding="utf-8"))} if a.docs else {}
        sp = make_splits(a.pairs, Path("data") / a.version, a.split, pub)
        ev = [json.loads(l)["src"] for l in open(a.eval_set, encoding="utf-8")] if a.eval_set else []
        print(json.dumps({"sizes": {k: len(v) for k, v in sp.items()}, "leakage": leakage(sp, ev)}, ensure_ascii=False))
    else:
        print(json.dumps(train(a.version, a.pairs, a.epochs, a.lr, a.batch, split=a.split, docs=a.docs, eval_set=a.eval_set,
                               placeholders=a.placeholders),
                         ensure_ascii=False))
