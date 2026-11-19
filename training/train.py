"""pairs.jsonl(passed=true) → data/v<N>/{train,valid,test}.jsonl(문서 단위 분할) → KoBART 전체 파인튜닝(MPS).

`python -m training.train --version v1 [--pairs data/pairs.jsonl] [--epochs 3]`
결과: models/<version>/hf/ (HF 체크포인트, export.py 입력) + train_metrics.json
"""
import argparse, hashlib, json, random, time
from pathlib import Path

BASE = "gogamza/kobart-base-v2"
EOS = 1  # KoBART: bos = eos = decoder_start = 1
SEED = 0


def split_of(doc_id):
    """문서 id 해시로 고정 분할(8:1:1). 같은 문서의 문장은 항상 같은 쪽."""
    b = int(hashlib.sha1(doc_id.encode()).hexdigest(), 16) % 10
    return "test" if b == 0 else "valid" if b == 1 else "train"


def make_splits(pairs_paths, out_dir):
    splits = {"train": [], "valid": [], "test": []}
    for path in pairs_paths:
        for line in Path(path).open(encoding="utf-8"):
            p = json.loads(line)
            if p.get("passed") and p.get("tgt"):
                splits[split_of(p["doc_id"])].append({"doc_id": p["doc_id"], "src": p["src"], "tgt": p["tgt"]})
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


def train(version, pairs_paths, epochs=3, lr=3e-5, batch=8, data_root="data", model_root="models"):
    import torch
    from transformers import AutoTokenizer, BartForConditionalGeneration

    random.seed(SEED)
    torch.manual_seed(SEED)
    torch.use_deterministic_algorithms(True, warn_only=True)
    snapshot = Path(data_root) / version
    splits = make_splits(pairs_paths, snapshot)
    tok = AutoTokenizer.from_pretrained(BASE)
    model = BartForConditionalGeneration.from_pretrained(BASE)
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model.to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=lr)
    train_data, valid_data = encode(tok, splits["train"]), encode(tok, splits["valid"])
    rng, history, t0 = random.Random(SEED), [], time.time()
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
    out = Path(model_root) / version / "hf"
    model.save_pretrained(out)
    tok.save_pretrained(out)
    metrics = {"base_model": BASE, "data_snapshot": str(snapshot), "device": device, "seed": SEED, "epochs": epochs,
               "lr": lr, "batch": batch, "train_seconds": round(time.time() - t0, 1),
               "sizes": {k: len(v) for k, v in splits.items()}, "history": history}
    (out / "train_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=1), encoding="utf-8")
    return metrics


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--pairs", nargs="+", default=["data/pairs.jsonl"])
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--lr", type=float, default=3e-5)
    ap.add_argument("--batch", type=int, default=8)
    a = ap.parse_args()
    print(json.dumps(train(a.version, a.pairs, a.epochs, a.lr, a.batch), ensure_ascii=False))
