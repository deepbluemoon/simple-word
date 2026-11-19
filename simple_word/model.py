import json
from pathlib import Path

from simple_word.numbers import numbers
from simple_word.placeholders import TOKENS as PH_TOKENS, mask, unmask
from simple_word.terms import missing_terms, preserve_terms

EOS = 1  # KoBART: bos = eos = decoder_start = 1


class Simplifier:
    """models/<version>/ 의 ONNX(INT8)를 onnxruntime(CPU)으로 불러 탐욕 디코딩(결정적, self-attention KV 캐시).

    artifact_dir 에 encoder.onnx 가 없을 때만 입력을 그대로 돌려주는 더미로 동작한다.
    숫자 안전장치: 출력의 숫자·날짜·금액·비율이 원문과 다르면(100분의 20 = 20% 는 같음) 그 문장은 원문을 돌려준다.
    보존 용어 안전장치: 원문의 보존 용어(simple_word/preserve_terms.txt)가 출력에서 빠져도 원문을 돌려준다.
    255토큰을 넘는 입력도 원문을 돌려준다. 둘 다 fallback 으로 표시한다.
    자리표시자 모델(tokenizer에 <N0>이 있음, v3~): 숫자·보존 용어를 <N0>·<T0>로 바꿔 넣고 출력에서 되돌린다.
    출력에 자리표시자가 빠지거나 모르는 것이 있으면 원문을 돌려준다(사유 placeholder).
    """

    def __init__(self, artifact_dir: str, force_placeholders: bool | None = None):
        self.artifact_dir = Path(artifact_dir)
        self.dummy = not (self.artifact_dir / "encoder.onnx").exists()
        if self.dummy:
            return
        import onnxruntime as ort
        from tokenizers import Tokenizer

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1  # 스레드 수에 따라 부동소수 합 순서가 달라지지 않게
        load = lambda f: ort.InferenceSession(str(self.artifact_dir / f), opts, providers=["CPUExecutionProvider"])
        self.encoder, self.decoder = load("encoder.onnx"), load("decoder.onnx")
        self.tok = Tokenizer.from_file(str(self.artifact_dir / "tokenizer.json"))
        self.tok.no_padding()
        self.tok.no_truncation()
        self.placeholders = self.tok.token_to_id("<N0>") is not None
        # 자리표시자를 다 쓰기 전에는 EOS를 막을지: metadata.json decoding.force_placeholders (기본 False).
        # 켜면 fallback은 줄지만 빠진 숫자를 엉뚱한 문장에 붙여 뜻이 틀릴 수 있다 (docs/T6_V3.md 비교).
        if force_placeholders is None:
            meta = self.artifact_dir / "metadata.json"
            try:
                force_placeholders = bool(json.loads(meta.read_text(encoding="utf-8")).get("decoding", {}).get("force_placeholders"))
            except (OSError, ValueError):
                force_placeholders = False
        self.force_placeholders = force_placeholders

    def simplify(self, sentences: list[str]) -> list[str]:
        return [text for text, _ in self.simplify_detailed(sentences)]

    def simplify_detailed(self, sentences: list[str]) -> list[tuple[str, bool]]:
        """[(출력, 원문으로 대체했는지)]."""
        return [(output, fallback) for output, fallback, _ in self.simplify_explained(sentences)]

    def simplify_explained(self, sentences: list[str]) -> list[tuple[str, bool, str | None]]:
        """[(출력, 원문 대체 여부, 사유)]. 상태는 저장하지 않아 여러 요청이 함께 써도 안전하다."""
        if self.dummy:
            return [(s, False, None) for s in sentences]
        out = []
        for s in sentences:
            if getattr(self, "placeholders", False):
                masked, slots = mask(s)
                y = self._one(masked, slots=slots, force=getattr(self, "force_placeholders", False))
                if y is not None:
                    y = unmask(y, slots)
                    if y is None:
                        out.append((s, True, "placeholder"))
                        continue
            else:
                y = self._one(s)
            if y is None:
                out.append((s, True, "length"))
            elif numbers(y) != numbers(s):
                out.append((s, True, "numbers"))
            elif missing_terms(s, y, preserve_terms()):
                out.append((s, True, "preserve"))
            else:
                out.append((y, False, None))
        return out

    def _one(self, text, max_len=256, slots=None, force=False):
        """탐욕 디코딩. slots(자리표시자 모델)를 주면 입력에 없는 자리표시자는 내지 않는다.
        force면 입력의 자리표시자를 모두 쓰기 전에는 문장을 끝내지 않는다(EOS 막음)."""
        import numpy as np

        ids = self.tok.encode(text, add_special_tokens=False).ids
        if len(ids) > max_len - 1:  # 255토큰 초과: 잘라서 바꾸면 뒷부분 정보가 사라지므로 원문 그대로
            return None
        ids = ids + [EOS]
        x = np.array([ids], dtype=np.int64)
        mask = np.ones_like(x)
        cross = self.encoder.run(None, {"input_ids": x, "attention_mask": mask})  # 층별 cross K/V, 한 번만
        feed = {"attention_mask": mask}
        feed.update((o.name, c) for o, c in zip(self.encoder.get_outputs(), cross))
        heads, hd = cross[0].shape[1], cross[0].shape[3]
        past_names = [i.name for i in self.decoder.get_inputs() if i.name.startswith("past_")]
        past = [np.zeros((1, heads, 0, hd), dtype=np.float32) for _ in past_names]  # KV 캐시, 처음엔 길이 0
        out = [EOS]
        need, banned = set(), []
        if slots is not None:
            ph = {t: self.tok.token_to_id(t) for t in PH_TOKENS}
            need = {ph[t] for t in slots}
            banned = [i for t, i in ph.items() if t not in slots and i is not None]
        for step in range(min(2 * len(ids) + 16, max_len)):
            feed.update(zip(past_names, past))
            feed["input_ids"] = np.array([[out[-1]]], dtype=np.int64)
            feed["position_ids"] = np.array([[step]], dtype=np.int64)
            logits, *past = self.decoder.run(None, feed)
            row = logits[0, -1]
            if slots is not None:
                row = row.copy()
                row[banned] = -np.inf
                if force and need - set(out):
                    row[EOS] = -np.inf
            nxt = int(row.argmax())
            if nxt == EOS:
                break
            out.append(nxt)
        return self.tok.decode(out[1:], skip_special_tokens=True).strip()
