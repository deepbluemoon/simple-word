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
    for text, got in zip(texts, [simp._one(t) for t in texts]):  # 숫자 안전장치 전 디코딩 출력
        ids = tok(text, add_special_tokens=False)["input_ids"] + [1]
        gen = model.generate(torch.tensor([ids]), do_sample=False, num_beams=1, max_new_tokens=min(2 * len(ids) + 16, 256),
                             min_length=0, decoder_start_token_id=1, eos_token_id=1, pad_token_id=3)
        assert got == tok.decode(gen[0], skip_special_tokens=True).strip()
    assert simp.simplify(texts) == simp.simplify(texts)
    assert Path(tmp_path / "models/t/parity.jsonl").read_text().count("\n") == 20 and meta["version"] == "t"


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
    simp._one = outputs.get
    src = list(outputs)
    assert simp.simplify_detailed(src) == [("과태료의 20%를 줄여 줍니다.", False), ("20일 이내에 신청하여야 합니다.", True),
                                           ("신청은 행정복지센터에서 받아요.", False)]
    assert simp.simplify(src) == [t for t, _ in simp.simplify_detailed(src)]  # 길이·순서·결정성 그대로


def test_preserved_term_guard_falls_back_when_term_dropped():
    simp = Simplifier.__new__(Simplifier)
    simp.dummy = False
    outputs = {"주민등록증 진위확인 서비스를 이용한다.": "주민증을 확인하는 서비스를 써요.",  # 보존 용어 빠짐 → 원문 (v2 test 실제 사례)
               "주민등록증을 재발급받을 수 있다.": "주민등록증을 다시 받을 수 있어요."}  # 유지 → 모델 출력
    simp._one = outputs.get
    assert simp.simplify_detailed(list(outputs)) == [("주민등록증 진위확인 서비스를 이용한다.", True),
                                                     ("주민등록증을 다시 받을 수 있어요.", False)]
