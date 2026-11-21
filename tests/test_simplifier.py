import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from simple_word.model import Simplifier, _read_metadata


@pytest.mark.parametrize("metadata,expected", [({}, 1), ({"decoding": {"num_beams": 4}}, 4)])
def test_num_beams_defaults_and_accepts_only_integer_metadata(tmp_path, metadata, expected):
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps(metadata), encoding="utf-8")
    assert _read_metadata(path).get("decoding", {}).get("num_beams", 1) == expected


@pytest.mark.parametrize("metadata", [
    [], {"decoding": None}, {"decoding": []}, {"decoding": {"num_beams": None}},
    {"decoding": {"num_beams": "four"}}, {"decoding": {"num_beams": 4.9}},
    {"decoding": {"num_beams": True}}, {"decoding": {"num_beams": 0}},
])
def test_num_beams_invalid_metadata_fails_clearly(tmp_path, metadata):
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError, match="metadata"):
        _read_metadata(path)


def test_hf_parity_reference_uses_requested_beam_settings(monkeypatch):
    from types import SimpleNamespace
    from training.export import _assert_parity, _generate_reference

    class Tokenizer:
        def get_vocab(self): return {}
        def encode(self, text, add_special_tokens=False): return [7, 8]
        def decode(self, ids, skip_special_tokens=True):
            ids = tuple(token for token in ids if token != 1)
            return {
                (7,): "신청 금액은 200원이며 안내를 확인하고 신청서를 제출하세요.",
                (8,): "신청 금액은 100원이며 안내를 확인하고 신청서를 제출해 주세요.",
                (9,): "짧은 결과",
                (10,): "신청 금액은 200원이고 신청서를 제출합니다.",
            }[tuple(ids)]

    class Model:
        def generate(self, **kwargs):
            self.kwargs = kwargs
            return [[1, token, 1] for token in (7, 8, 9, 10)]

    class LogitsProcessor: pass

    torch = SimpleNamespace(tensor=lambda value, **_: value, ones_like=lambda value: value,
                            long="long", inf=float("inf"))
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "transformers", SimpleNamespace(LogitsProcessor=LogitsProcessor))
    model = Model()
    source = "신청 금액은 100원이며 안내를 확인하고 신청서를 제출해야 합니다."
    output = _generate_reference(model, Tokenizer(), [source], 4, False, False)
    assert output == ["신청 금액은 100원이며 안내를 확인하고 신청서를 제출해 주세요."]
    assert model.kwargs["num_beams"] == 4
    assert model.kwargs["num_return_sequences"] == 4
    assert model.kwargs["length_penalty"] == 1.0
    assert model.kwargs["early_stopping"] is False
    _assert_parity(output, output)
    with pytest.raises(RuntimeError, match="HF generate parity mismatch: 1/1"):
        _assert_parity(["HF output"], ["ONNX output"])


def test_int8_export_uses_onnx_outputs_for_parity_without_fp32_equality_check(tmp_path, monkeypatch):
    from training import export as export_module

    class HFModel:
        @classmethod
        def from_pretrained(cls, _path): return cls()
        def eval(self): return self
        def cpu(self): return self

    class HFTokenizer:
        @classmethod
        def from_pretrained(cls, _path): return cls()

    class ServingModel:
        placeholders = False
        def __init__(self, *_args, **_kwargs): pass
        def simplify(self, inputs): return [f"onnx:{text}" for text in inputs]

    monkeypatch.setitem(sys.modules, "transformers", SimpleNamespace(
        BartForConditionalGeneration=HFModel, AutoTokenizer=HFTokenizer))
    monkeypatch.setattr(export_module, "PARITY_INPUTS", ["input"])
    monkeypatch.setattr(export_module, "export_onnx", lambda _model, path: [
        (path / f"{name}.onnx").touch() for name in ("encoder", "decoder")])
    monkeypatch.setattr(export_module, "quantize", lambda _path: None)
    monkeypatch.setattr(export_module, "_generate_reference", lambda *_args: pytest.fail("INT8 must not require exact fp32 match"))
    monkeypatch.setattr(export_module, "_assert_parity", lambda *_args: pytest.fail("INT8 must not require exact fp32 match"))
    monkeypatch.setattr("simple_word.model.Simplifier", ServingModel)
    tokenizer_json = tmp_path / "tokenizer.json"
    tokenizer_json.write_text("{}", encoding="utf-8")

    metadata = export_module.export("int8-model", tmp_path / "models", hf_dir=tmp_path / "hf",
                                    tokenizer_json=tokenizer_json, int8=True)

    parity = json.loads((tmp_path / "models/int8-model/parity.jsonl").read_text(encoding="utf-8"))
    assert parity == {"input": "input", "output": "onnx:input"}
    assert metadata["quantization"] == "dynamic-int8"


def test_simplifier_is_dummy_without_model(tmp_path):
    assert Simplifier(str(tmp_path)).simplify(["가 나", "다"]) == ["가 나", "다"]


def test_onnx_path_loads_runtime_and_restores_required_placeholder(tmp_path, monkeypatch):
    import numpy as np

    artifact = tmp_path / "model"
    artifact.mkdir()
    (artifact / "encoder.onnx").touch()
    (artifact / "metadata.json").write_text(json.dumps({"decoding": {"force_placeholders": True}}))

    class Tokenizer:
        def no_padding(self): pass
        def no_truncation(self): pass
        def token_to_id(self, token): return 7 if token == "<N0>" else None
        def encode(self, text, add_special_tokens=False): return SimpleNamespace(ids=[2])
        def decode(self, ids, skip_special_tokens=True): return "지원금 <N0> 원을 신청합니다."

    class Encoder:
        def get_outputs(self): return [SimpleNamespace(name="cross_0")]
        def run(self, _, feed): return [np.zeros((1, 2, 1, 3), dtype=np.float32)]

    class Decoder:
        def __init__(self): self.calls = 0
        def get_inputs(self): return [SimpleNamespace(name="past_key")]
        def run(self, _, feed):
            assert "cross_0" in feed and "past_key" in feed
            logits = np.full((1, 1, 8), -1.0)
            logits[0, 0, 7 if self.calls == 0 else 1] = 1.0
            self.calls += 1
            return logits, np.zeros((1, 2, 1, 3), dtype=np.float32)

    encoder, decoder = Encoder(), Decoder()
    runtime = SimpleNamespace(SessionOptions=lambda: SimpleNamespace(), InferenceSession=lambda path, *_args, **_kwargs: decoder if path.endswith("decoder.onnx") else encoder)
    tokenizer = SimpleNamespace(from_file=lambda _: Tokenizer())
    monkeypatch.setitem(sys.modules, "onnxruntime", runtime)
    monkeypatch.setitem(sys.modules, "tokenizers", SimpleNamespace(Tokenizer=tokenizer))

    simp = Simplifier(str(artifact))

    assert simp.simplify_explained(["지원금 3억 원을 신청합니다."]) == [("지원금 3억 원을 신청합니다.", False, None)]
    assert decoder.calls == 2


def test_onnx_greedy_matches_torch_greedy(tmp_path, monkeypatch):
    torch = pytest.importorskip("torch")
    from transformers import AutoTokenizer, BartConfig, BartForConditionalGeneration
    import training.export as export_module
    monkeypatch.setattr(export_module, "PARITY_INPUTS", [
        "신청은 행정복지센터에서 받는다.", "과태료의 100분의 20을 감경합니다."
    ])

    tok = AutoTokenizer.from_pretrained("gogamza/kobart-base-v2")
    torch.manual_seed(0)
    cfg = BartConfig(vocab_size=len(tok), d_model=16, encoder_layers=1, decoder_layers=1, encoder_attention_heads=2,
                     decoder_attention_heads=2, encoder_ffn_dim=32, decoder_ffn_dim=32, max_position_embeddings=300,
                     bos_token_id=1, eos_token_id=1, pad_token_id=3, decoder_start_token_id=1, forced_bos_token_id=None, forced_eos_token_id=None)
    hf = tmp_path / "hf"
    BartForConditionalGeneration(cfg).save_pretrained(hf)
    tok.save_pretrained(hf)
    meta = export_module.export("t", tmp_path / "models", hf_dir=hf, int8=False)
    simp = Simplifier(str(tmp_path / "models/t"))
    texts = ["신청은 행정복지센터에서 받는다.", "과태료의 100분의 20을 감경합니다."]
    model = BartForConditionalGeneration.from_pretrained(hf).eval()
    for text, got in zip(texts, [simp._candidates(t)[0] for t in texts]):  # 숫자 안전장치 전 디코딩 출력
        ids = tok(text, add_special_tokens=False)["input_ids"] + [1]
        gen = model.generate(torch.tensor([ids]), do_sample=False, num_beams=1, max_new_tokens=min(2 * len(ids) + 16, 256),
                             min_length=0, decoder_start_token_id=1, eos_token_id=1, pad_token_id=3)
        assert got == tok.decode(gen[0], skip_special_tokens=True).strip()
    beam_meta = export_module.export("t-beam", tmp_path / "models", hf_dir=hf, int8=False, num_beams=2)
    beam_simp = Simplifier(str(tmp_path / "models/t-beam"))
    for text in texts:
        ids = tok(text, add_special_tokens=False)["input_ids"] + [1]
        gen = model.generate(torch.tensor([ids]), do_sample=False, num_beams=2, length_penalty=1.0,
                             early_stopping=False, max_new_tokens=min(2 * len(ids) + 16, 256), min_length=0,
                             decoder_start_token_id=1, eos_token_id=1, pad_token_id=3,
                             forced_bos_token_id=None, forced_eos_token_id=None)
        assert beam_simp._candidates(text)[0] == tok.decode(gen[0], skip_special_tokens=True).strip()
    assert beam_meta["decoding"]["num_beams"] == 2
    assert simp.simplify(texts) == simp.simplify(texts)
    assert Path(tmp_path / "models/t/parity.jsonl").read_text().count("\n") == len(texts) and meta["version"] == "t"
    assert meta["decoding"]["num_beams"] == 1


def test_input_over_255_tokens_is_returned_unchanged():
    class Tok:
        def encode(self, text, add_special_tokens=False):
            return type("E", (), {"ids": [7] * 256})()

    simp = Simplifier.__new__(Simplifier)  # 모델 없이 _one 의 길이 가드만 확인 (가드가 없으면 encoder=None 에서 터짐)
    simp.dummy, simp.tok, simp.encoder = False, Tok(), None
    assert simp.simplify(["아주 긴 문장"]) == ["아주 긴 문장"]


def test_number_guard_falls_back_only_when_numbers_differ():
    simp = Simplifier.__new__(Simplifier)
    simp.dummy = False
    outputs = {"과태료의 100분의 20을 감경합니다.": "과태료의 20%를 줄여 줍니다.",  # 같은 값 → 모델 출력 유지
               "20일 이내에 신청하여야 합니다.": "2일 안에 신청해야 해요.",  # 숫자 바뀜 → 원문
               "신청은 행정복지센터에서 받는다.": "신청은 행정복지센터에서 받아요."}
    simp._candidates = lambda text, *_args: [outputs.get(text)]
    src = list(outputs)
    assert simp.simplify_detailed(src) == [("과태료의 20%를 줄여 줍니다.", False), ("20일 이내에 신청하여야 합니다.", True),
                                           ("신청은 행정복지센터에서 받아요.", False)]
    assert simp.simplify(src) == [t for t, _ in simp.simplify_detailed(src)]  # 길이·순서·결정성 그대로


def test_preserved_term_guard_falls_back_when_term_dropped():
    simp = Simplifier.__new__(Simplifier)
    simp.dummy = False
    outputs = {"주민등록증 진위확인 서비스를 이용한다.": "주민증을 확인하는 서비스를 써요.",  # 보존 용어 빠짐 → 원문 (v2 test 실제 사례)
               "주민등록증을 재발급받을 수 있다.": "주민등록증을 다시 받을 수 있어요."}  # 유지 → 모델 출력
    simp._candidates = lambda text, *_args: [outputs.get(text)]
    assert simp.simplify_detailed(list(outputs)) == [("주민등록증 진위확인 서비스를 이용한다.", True),
                                                     ("주민등록증을 다시 받을 수 있어요.", False)]


def test_simplifier_explains_number_term_and_length_fallbacks():
    simp = Simplifier.__new__(Simplifier)
    simp.dummy = False
    outputs = {
        "20일 안에 신청합니다.": "2일 안에 신청합니다.",
        "주민등록증 진위확인 서비스입니다.": "주민증 확인 서비스입니다.",
        "아주 긴 문장입니다.": None,
    }
    simp._candidates = lambda text, *_args: [outputs.get(text)]

    explained = simp.simplify_explained(list(outputs))

    assert explained == [
        ("20일 안에 신청합니다.", True, "numbers"),
        ("주민등록증 진위확인 서비스입니다.", True, "preserve"),
        ("아주 긴 문장입니다.", True, "length"),
    ]
    assert simp.simplify_detailed(list(outputs)) == [(text, fallback) for text, fallback, _ in explained]


def test_beam_uses_next_candidate_when_top_candidate_fails_number_guard(monkeypatch):
    import numpy as np

    class Tok:
        def encode(self, _text, add_special_tokens=False):
            return type("E", (), {"ids": [7]})()

        def decode(self, ids, skip_special_tokens=True):
            return {2: "2일 이내에 접수합니다.", 3: "20일 이내에 접수합니다."}.get(ids[0], "")

    class Encoder:
        def run(self, _outputs, _inputs):
            return [np.zeros((1, 1, 1, 1), dtype=np.float32)]

        def get_outputs(self):
            return [type("O", (), {"name": "cross_k"})()]

    class Decoder:
        def __init__(self): self.batch_sizes = []

        def get_inputs(self):
            return [type("I", (), {"name": "past_key"})(), type("I", (), {"name": "cross_k"})()]

        def run(self, _outputs, inputs):
            batch = inputs["input_ids"].shape[0]
            self.batch_sizes.append(batch)
            logits = np.full((batch, 1, 8), -30.0)
            if inputs["position_ids"][0, 0] == 0:
                logits[0, 0, 2], logits[0, 0, 3] = 5.0, 4.0
            else:
                for row in range(batch):
                    logits[row, 0, 1] = 5.0
                    logits[row, 0, 4 + row] = -5.0
            return [logits, np.zeros((batch, 1, inputs["position_ids"][0, 0] + 1, 1), dtype=np.float32)]

    simp = Simplifier.__new__(Simplifier)
    simp.dummy, simp.tok, simp.encoder, simp.decoder = False, Tok(), Encoder(), Decoder()
    simp.placeholders, simp.num_beams = False, 2
    monkeypatch.setattr("simple_word.model.preserve_terms", lambda: [])

    assert simp.simplify_explained(["20일 이내에 접수합니다."]) == [
        ("20일 이내에 접수합니다.", False, None)
    ]
    assert simp.decoder.batch_sizes == [1, 2, 2]  # 상한에 도달하기 전까지 살아 있는 빔을 함께 탐색


def test_beam_uses_global_top_two_width_and_ignores_lower_ranked_eos():
    import numpy as np

    class Tok:
        def encode(self, _text, add_special_tokens=False): return type("E", (), {"ids": [7]})()
        def decode(self, ids, skip_special_tokens=True):
            return {(1,): "", (2, 1): "early-two", (2, 4, 1): "branch-two",
                    (3, 5, 1): "branch-three"}.get(tuple(ids), "other")

    class Encoder:
        def run(self, *_args): return [np.zeros((1, 1, 1, 1), dtype=np.float32)]
        def get_outputs(self): return [type("O", (), {"name": "cross_k"})()]

    class Decoder:
        def __init__(self): self.batch_sizes = []
        def get_inputs(self): return [type("I", (), {"name": "cross_k"})()]
        def run(self, _outputs, feed):
            batch = feed["input_ids"].shape[0]
            step = int(feed["position_ids"][0, 0])
            self.batch_sizes.append(batch)
            logits = np.full((batch, 1, 8), -100.0, dtype=np.float32)
            if step == 0:
                logits[0, 0, 2:5] = [10.0, 9.0, 7.0]
                logits[0, 0, 1] = 8.0  # global rank 2: EOS must be ignored
            elif step == 1:
                logits[0, 0, 1], logits[0, 0, 4] = 10.0, 9.9
                logits[1, 0, 1], logits[1, 0, 5] = 8.0, 7.0  # EOS rank 2 ignored
            else:
                logits[:, 0, 1] = 10.0
                logits[:, 0, 6] = 9.0
            return [logits]

    simp = Simplifier.__new__(Simplifier)
    simp.dummy, simp.tok, simp.encoder, simp.decoder = False, Tok(), Encoder(), Decoder()
    simp.num_beams = 2

    outputs = simp._candidates("source")

    assert "" not in outputs
    assert "early-two" in outputs
    assert simp.decoder.batch_sizes[:3] == [1, 2, 2]


def test_beam_keeps_searching_when_a_live_beam_can_improve_with_length_penalty():
    import numpy as np

    class Tok:
        def encode(self, _text, add_special_tokens=False): return type("E", (), {"ids": [7]})()
        def decode(self, ids, skip_special_tokens=True):
            return {(2, 1): "short-finish", (2, 4, 1): "early-finish",
                    (2, 4, 6, 1): "best-continuation", (3, 1): "other-finish"}.get(tuple(ids), "other")

    class Encoder:
        def run(self, *_args): return [np.zeros((1, 1, 1, 1), dtype=np.float32)]
        def get_outputs(self): return [type("O", (), {"name": "cross_k"})()]

    class Decoder:
        def __init__(self): self.batch_sizes = []
        def get_inputs(self): return [type("I", (), {"name": "cross_k"})()]
        def run(self, _outputs, feed):
            batch = feed["input_ids"].shape[0]
            step = int(feed["position_ids"][0, 0])
            self.batch_sizes.append(batch)
            logits = np.full((batch, 1, 8), -100.0, dtype=np.float32)
            if step == 0:
                logits[0, 0, 2:4] = 10.0
            elif step == 1:
                logits[0, 0, 1], logits[0, 0, 4] = 10.0, 10.0
                logits[1, 0, 1], logits[1, 0, 5] = 10.0, 4.0
            elif step == 2:
                logits[0, 0, 6], logits[0, 0, 1] = 10.0, -20.0
                logits[1, 0, 1] = 10.0
            else:
                logits[0, 0, 1] = 10.0
                logits[1, 0, 7] = 10.0
            return [logits]

    simp = Simplifier.__new__(Simplifier)
    simp.dummy, simp.tok, simp.encoder, simp.decoder = False, Tok(), Encoder(), Decoder()
    simp.num_beams = 2

    outputs = simp._candidates("source")

    assert "best-continuation" in outputs
    assert simp.decoder.batch_sizes == [1, 2, 2, 2]


def test_empty_and_short_beam_candidates_are_skipped():
    simp = Simplifier.__new__(Simplifier)
    simp.dummy, simp.placeholders, simp.num_beams = False, False, 4
    simp._candidates = lambda _text, *_args: ["", "짧음", "가" * 10]
    assert simp.simplify_explained(["가" * 20]) == [("가" * 10, False, None)]


def test_greedy_preserves_outputs_shorter_than_half_the_source():
    simp = Simplifier.__new__(Simplifier)
    simp.dummy, simp.placeholders, simp.num_beams = False, False, 1
    simp._candidates = lambda _text, *_args: ["가" * 9]
    assert simp.simplify_explained(["가" * 20]) == [("가" * 9, False, None)]


def test_greedy_stops_when_eos_is_the_best_token():
    import numpy as np

    class Tok:
        def encode(self, _text, add_special_tokens=False): return type("E", (), {"ids": [7]})()
        def decode(self, ids, skip_special_tokens=True): return ""

    class Encoder:
        def run(self, *_args): return [np.zeros((1, 1, 1, 1), dtype=np.float32)]
        def get_outputs(self): return [type("O", (), {"name": "cross_k"})()]

    class Decoder:
        def __init__(self): self.calls = 0
        def get_inputs(self): return [type("I", (), {"name": "cross_k"})()]
        def run(self, *_args):
            self.calls += 1
            logits = np.full((1, 1, 8), -100.0, dtype=np.float32)
            logits[0, 0, 1], logits[0, 0, 2] = 10.0, 9.0
            return [logits]

    simp = Simplifier.__new__(Simplifier)
    simp.dummy, simp.tok, simp.encoder, simp.decoder = False, Tok(), Encoder(), Decoder()
    simp.num_beams = 1
    assert simp._candidates("source") == [""]
    assert simp.decoder.calls == 1


def test_all_negative_infinity_logits_report_decode_or_placeholder_fallback(monkeypatch):
    import numpy as np
    import simple_word.model as model_module

    class Tok:
        def encode(self, _text, add_special_tokens=False): return type("E", (), {"ids": [7]})()
        def token_to_id(self, _token): return 2

    class Encoder:
        def run(self, *_args): return [np.zeros((1, 1, 1, 1), dtype=np.float32)]
        def get_outputs(self): return [type("O", (), {"name": "cross_k"})()]

    class Decoder:
        def get_inputs(self): return [type("I", (), {"name": "cross_k"})()]
        def run(self, _outputs, feed):
            return [np.full((feed["input_ids"].shape[0], 1, 8), -np.inf, dtype=np.float32)]

    simp = Simplifier.__new__(Simplifier)
    simp.dummy, simp.tok, simp.encoder, simp.decoder = False, Tok(), Encoder(), Decoder()
    simp.placeholders, simp.num_beams, simp.force_placeholders = False, 2, False
    monkeypatch.setattr(model_module, "preserve_terms", lambda: [])
    assert simp.simplify_explained(["원문입니다."]) == [("원문입니다.", True, "decode")]

    simp.placeholders, simp.force_placeholders = True, True
    monkeypatch.setattr(model_module, "mask", lambda _text: ("masked", ["<N0>"]))
    assert simp.simplify_explained(["원문입니다."]) == [("원문입니다.", True, "placeholder")]
