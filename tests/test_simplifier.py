from pathlib import Path

import pytest

from simple_word.model import Simplifier


def test_simplifier_is_dummy_without_model(tmp_path):
    assert Simplifier(str(tmp_path)).simplify(["가 나", "다"]) == ["가 나", "다"]


def test_onnx_greedy_matches_torch_greedy(tmp_path):
    torch = pytest.importorskip("torch")
    from transformers import AutoTokenizer, BartConfig, BartForConditionalGeneration
    from training.export import export

    tok = AutoTokenizer.from_pretrained("gogamza/kobart-base-v2")
    torch.manual_seed(0)
    cfg = BartConfig(vocab_size=len(tok), d_model=16, encoder_layers=1, decoder_layers=1, encoder_attention_heads=2,
                     decoder_attention_heads=2, encoder_ffn_dim=32, decoder_ffn_dim=32, max_position_embeddings=300,
                     bos_token_id=1, eos_token_id=1, pad_token_id=3, decoder_start_token_id=1, forced_bos_token_id=None, forced_eos_token_id=None)
    hf = tmp_path / "hf"
    BartForConditionalGeneration(cfg).save_pretrained(hf)
    tok.save_pretrained(hf)
    meta = export("t", tmp_path / "models", hf_dir=hf, int8=False)
    simp = Simplifier(str(tmp_path / "models/t"))
    texts = ["신청은 행정복지센터에서 받는다.", "과태료의 100분의 20을 감경합니다."]
    model = BartForConditionalGeneration.from_pretrained(hf).eval()
    for text, got in zip(texts, simp.simplify(texts)):
        ids = tok(text, add_special_tokens=False)["input_ids"] + [1]
        gen = model.generate(torch.tensor([ids]), do_sample=False, num_beams=1, max_new_tokens=min(2 * len(ids) + 16, 256),
                             min_length=0, decoder_start_token_id=1, eos_token_id=1, pad_token_id=3)
        assert got == tok.decode(gen[0], skip_special_tokens=True).strip()
    assert simp.simplify(texts) == simp.simplify(texts)
    assert Path(tmp_path / "models/t/parity.jsonl").read_text().count("\n") == 20 and meta["version"] == "t"
