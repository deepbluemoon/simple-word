"""models/<version>/hf → models/<version>/{encoder,decoder}.onnx(INT8 동적 양자화) + tokenizer.json + metadata.json + parity.jsonl.

`python -m training.export --version v1`
"""
import argparse, datetime as dt, json, shutil, tempfile
from pathlib import Path

# 고정 parity 입력 20문장(바꾸지 말 것: 서빙 컨테이너 출력과 비교하는 기준)
PARITY_INPUTS = [
    "본 사업은 관내 거주 만 65세 이상 기초생활수급자를 대상으로 하며, 신청을 희망하는 자는 구비서류를 지참하여 주소지 관할 행정복지센터에 방문 접수하여야 합니다.",
    "과태료 부과 사전통지서를 송달받은 날부터 20일 이내에 의견제출 기한 내 자진납부 시 과태료의 100분의 20에 해당하는 금액을 감경합니다.",
    "동절기 수도계량기 동파 방지를 위하여 계량기함 내부를 보온재로 충전하여 주시기 바랍니다.",
    "신청 기간은 2026년 12월 1일부터 12월 31일까지이며, 기한 내 미신청 시 지원 대상에서 제외됩니다.",
    "지원 금액은 가구당 월 최대 30만 원이며, 소득 기준을 충족하는 경우에 한하여 지급합니다.",
    "구비서류는 신분증, 주민등록등본, 소득증빙서류 각 1부입니다.",
    "행정안전부는 겨울철 대설·한파에 대비하여 관계기관 합동 점검을 실시하였다.",
    "보건복지부는 취약계층 보호를 위해 긴급복지 지원 기준을 완화한다고 밝혔다.",
    "체납된 지방세는 가산금이 부과되므로 납부기한 내에 납부하시기 바랍니다.",
    "본인부담금은 진료비의 100분의 30으로 하되, 차상위계층은 100분의 14로 합니다.",
    "주민등록증 재발급은 가까운 행정복지센터에서 신청할 수 있습니다.",
    "사업 참여를 희망하는 기관은 11월 30일까지 사업계획서를 제출하여야 한다.",
    "독거노인·노숙인 등 취약계층에 대한 안전확인을 강화하고 한파쉼터 운영상태를 점검한다.",
    "이번 개정안은 공포 후 6개월이 경과한 날부터 시행한다.",
    "의료급여 수급권자는 1종과 2종으로 구분되며, 본인부담 수준이 다르다.",
    "근로장려금은 매년 5월에 신청하며, 요건을 충족하는 가구에 9월까지 지급된다.",
    "AI 기반 민원 안내 서비스를 전국 지방정부로 확대한다.",
    "재난 발생 시 주민대피지원단이 고령자와 장애인의 대피를 돕는다.",
    "정부는 생활인구 데이터를 활용해 인구감소지역 맞춤형 정책을 마련할 계획이다.",
    "자세한 사항은 보건복지상담센터(129)로 문의하시기 바랍니다.",
]


def export_onnx(model, out_dir, opset=17):
    """encoder.onnx: 원문 → 디코더 층마다 cross-attention K/V (한 번만 계산).
    decoder.onnx: 토큰 1개 + 위치 + self-attention 과거 K/V(길이 0 가능) + cross K/V → logits, 새 self K/V.
    HF 디코더 층(post-LN BART)을 그대로 따라 짠 것. torch generate 와의 일치는 tests/test_simplifier.py 가 확인한다.
    """
    import torch

    model = model.eval().cpu().requires_grad_(False)
    dec = model.get_decoder()
    heads = model.config.decoder_attention_heads
    L = len(dec.layers)

    def split(x):  # [b, s, d] → [b, heads, s, hd]
        return x.reshape(x.shape[0], -1, heads, x.shape[-1] // heads).transpose(1, 2)

    def attend(q, k, v, scaling, add_mask=None):
        w = split(q) @ k.transpose(-1, -2) * scaling
        if add_mask is not None:
            w = w + add_mask
        o = w.softmax(-1) @ v
        return o.transpose(1, 2).reshape(q.shape)

    class Enc(torch.nn.Module):  # model 을 하위 모듈로 등록해야 가중치가 상수가 아닌 initializer 로 들어감
        def __init__(self):
            super().__init__()
            self.m = model

        def forward(self, input_ids, attention_mask):
            h = self.m.get_encoder()(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
            out = []
            for layer in dec.layers:
                out += [split(layer.encoder_attn.k_proj(h)), split(layer.encoder_attn.v_proj(h))]
            return tuple(out)

    class Dec(Enc):
        def forward(self, input_ids, position_ids, attention_mask, *kv):  # kv = past_k0, past_v0, ..., cross_k0, cross_v0, ...
            past, cross = kv[: 2 * L], kv[2 * L :]
            add_mask = (1.0 - attention_mask[:, None, None, :].float()) * torch.finfo(torch.float32).min
            h = dec.embed_tokens(input_ids) + dec.embed_positions.weight[position_ids + dec.embed_positions.offset]
            h = dec.layernorm_embedding(h)
            present = []
            for i, layer in enumerate(dec.layers):
                sa = layer.self_attn
                k = torch.cat([past[2 * i], split(sa.k_proj(h))], dim=2)
                v = torch.cat([past[2 * i + 1], split(sa.v_proj(h))], dim=2)
                present += [k, v]
                h = layer.self_attn_layer_norm(h + sa.out_proj(attend(sa.q_proj(h), k, v, sa.scaling)))
                ca = layer.encoder_attn
                h = layer.encoder_attn_layer_norm(h + ca.out_proj(attend(ca.q_proj(h), cross[2 * i], cross[2 * i + 1], ca.scaling, add_mask)))
                h = layer.final_layer_norm(h + layer.fc2(layer.activation_fn(layer.fc1(h))))
            return (self.m.lm_head(h) + self.m.final_logits_bias, *present)

    x = torch.tensor([[5, 6, 7, 1]])
    m = torch.ones_like(x)
    kv_names = lambda p: [f"{p}_{kind}{i}" for i in range(L) for kind in ("k", "v")]
    with torch.no_grad():
        cross = Enc()(x, m)
        torch.onnx.export(Enc(), (x, m), out_dir / "encoder.onnx", input_names=["input_ids", "attention_mask"],
                          output_names=kv_names("cross"), opset_version=opset, dynamo=False,
                          dynamic_axes={"input_ids": {1: "src"}, "attention_mask": {1: "src"}, **{n: {2: "src"} for n in kv_names("cross")}})
        past = tuple(torch.zeros(1, heads, 2, c.shape[-1]) for c in cross)
        torch.onnx.export(Dec(), (torch.tensor([[5]]), torch.tensor([[2]]), m, *past, *cross), out_dir / "decoder.onnx",
                          input_names=["input_ids", "position_ids", "attention_mask", *kv_names("past"), *kv_names("cross")],
                          output_names=["logits", *kv_names("present")], opset_version=opset, dynamo=False,
                          dynamic_axes={"input_ids": {0: "beam", 1: "tgt"}, "position_ids": {0: "beam", 1: "tgt"},
                                        "attention_mask": {0: "beam", 1: "src"},
                                        **{n: {0: "beam", 2: "past"} for n in kv_names("past")},
                                        **{n: {0: "beam", 2: "src"} for n in kv_names("cross")},
                                        "logits": {0: "beam", 1: "tgt"},
                                        **{n: {0: "beam", 2: "past1"} for n in kv_names("present")}})


def quantize(out_dir):
    from onnxruntime.quantization import QuantType, quantize_dynamic

    for name in ("encoder", "decoder"):
        fp32 = out_dir / f"{name}.fp32.onnx"
        (out_dir / f"{name}.onnx").rename(fp32)
        quantize_dynamic(fp32, out_dir / f"{name}.onnx", weight_type=QuantType.QInt8)
        fp32.unlink()


def dir_mb(path):
    return round(sum(f.stat().st_size for f in Path(path).iterdir() if f.is_file()) / 2**20, 1)


def _generate_reference(model, tokenizer, inputs, num_beams, placeholders, force_placeholders):
    import torch
    from transformers import LogitsProcessor
    from simple_word.numbers import numbers
    from simple_word.placeholders import TOKENS, mask, unmask
    from simple_word.terms import missing_terms, preserve_terms

    if type(num_beams) is not int or num_beams < 1:
        raise ValueError("num_beams must be an integer of at least 1")
    vocab = tokenizer.get_vocab()
    ph_ids = {term: vocab[term] for term in TOKENS if term in vocab}
    outputs = []
    for source in inputs:
        masked, slots = mask(source) if placeholders else (source, [])
        ids = tokenizer.encode(masked, add_special_tokens=False) + [1]
        input_ids = torch.tensor([ids], dtype=torch.long)
        bad_words = [[token_id] for token, token_id in ph_ids.items() if token not in slots]
        logits_processors = []
        required = {ph_ids[term] for term in slots if term in ph_ids} if force_placeholders else set()
        if required:
            class RequirePlaceholders(LogitsProcessor):
                def __call__(self, generated, scores):
                    scores = scores.clone()
                    for row, sequence in enumerate(generated.tolist()):
                        if not required.issubset(sequence):
                            scores[row, 1] = -torch.inf
                    return scores
            logits_processors.append(RequirePlaceholders())
        generated = model.generate(
            input_ids=input_ids, attention_mask=torch.ones_like(input_ids), do_sample=False,
            num_beams=num_beams, length_penalty=1.0, early_stopping=False,
            max_new_tokens=min(2 * len(ids) + 16, 256), min_length=0,
            decoder_start_token_id=1, eos_token_id=1, pad_token_id=3,
            forced_bos_token_id=None, forced_eos_token_id=None,
            bad_words_ids=bad_words or None, logits_processor=logits_processors or None,
        )
        text = tokenizer.decode(generated[0], skip_special_tokens=True).strip()
        text = unmask(text, slots) if placeholders else text
        if (text is None or not text or (num_beams > 1 and len(text) * 2 < len(source))
                or numbers(text) != numbers(source)
                or missing_terms(source, text, preserve_terms())):
            text = source
        outputs.append(text)
    return outputs


def hf_reference_outputs(hf_dir, inputs, num_beams, placeholders=False, force_placeholders=False):
    from transformers import AutoTokenizer, BartForConditionalGeneration
    model = BartForConditionalGeneration.from_pretrained(hf_dir).eval().cpu()
    tokenizer = AutoTokenizer.from_pretrained(hf_dir)
    return _generate_reference(model, tokenizer, inputs, num_beams, placeholders, force_placeholders)


def _assert_parity(reference, actual):
    if reference != actual:
        mismatches = sum(expected != got for expected, got in zip(reference, actual)) + abs(len(reference) - len(actual))
        first = next((index for index, pair in enumerate(zip(reference, actual)) if pair[0] != pair[1]), None)
        detail = f"; first mismatch at {first}: HF={reference[first]!r}, ONNX={actual[first]!r}" if first is not None else ""
        raise RuntimeError(f"HF generate parity mismatch: {mismatches}/{max(len(reference), len(actual))}{detail}")


def export(version, model_root="models", hf_dir=None, tokenizer_json=None, int8=True, force_placeholders=False, num_beams=1):
    from transformers import AutoTokenizer, BartForConditionalGeneration
    from simple_word.model import Simplifier

    if type(num_beams) is not int or num_beams < 1:
        raise ValueError("num_beams must be an integer of at least 1")
    out = Path(model_root) / version
    hf = Path(hf_dir or out / "hf")
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:  # 내보내기 중간 파일은 모델 폴더 밖에서
        tmp = Path(tmp)
        hf_model = BartForConditionalGeneration.from_pretrained(hf).eval().cpu()
        hf_tokenizer = AutoTokenizer.from_pretrained(hf)
        export_onnx(hf_model, tmp)
        if int8:
            quantize(tmp)
        for f in ("encoder.onnx", "decoder.onnx"):
            shutil.move(tmp / f, out / f)
    shutil.copy(tokenizer_json or hf / "tokenizer.json", out / "tokenizer.json")
    train_metrics = json.loads((hf / "train_metrics.json").read_text()) if (hf / "train_metrics.json").exists() else {}
    meta = {"version": version, "created_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "data_snapshot": train_metrics.get("data_snapshot"), "base_model": train_metrics.get("base_model"),
            "metrics": {"train": train_metrics, "model_dir_mb": None},
            "placeholders": False, "quantization": "dynamic-int8" if int8 else "fp32",
            "decoding": {"force_placeholders": force_placeholders, "num_beams": num_beams}}
    (out / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    simp = Simplifier(str(out), force_placeholders=force_placeholders)  # parity는 서빙과 같은 디코딩 설정으로
    meta["placeholders"] = simp.placeholders
    actual = simp.simplify(PARITY_INPUTS)
    if not int8:
        outputs = _generate_reference(hf_model, hf_tokenizer, PARITY_INPUTS, num_beams,
                                      simp.placeholders, force_placeholders)
        _assert_parity(outputs, actual)
    (out / "parity.jsonl").write_text("".join(json.dumps({"input": i, "output": o}, ensure_ascii=False) + "\n"
                                              for i, o in zip(PARITY_INPUTS, actual)), encoding="utf-8")
    meta["metrics"]["model_dir_mb"] = dir_mb(out)  # hf/ 하위 폴더는 제외, 서빙에 올리는 파일만
    (out / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return meta


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--models", default="models")
    ap.add_argument("--force-placeholders", action="store_true", help="자리표시자를 다 쓰기 전 EOS 막기(서빙 설정으로 metadata에 기록)")
    ap.add_argument("--num-beams", type=int, default=1)
    a = ap.parse_args()
    print(json.dumps(export(a.version, a.models, force_placeholders=a.force_placeholders,
                           num_beams=a.num_beams)["metrics"]["model_dir_mb"]))
