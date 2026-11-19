from pathlib import Path

from simple_word.numbers import numbers
from simple_word.terms import missing_terms, preserve_terms

EOS = 1  # KoBART: bos = eos = decoder_start = 1


class Simplifier:
    """models/<version>/ 의 ONNX(INT8)를 onnxruntime(CPU)으로 불러 탐욕 디코딩(결정적, self-attention KV 캐시).

    artifact_dir 에 encoder.onnx 가 없을 때만 입력을 그대로 돌려주는 더미로 동작한다.
    숫자 안전장치: 출력의 숫자·날짜·금액·비율이 원문과 다르면(100분의 20 = 20% 는 같음) 그 문장은 원문을 돌려준다.
    보존 용어 안전장치: 원문의 보존 용어(simple_word/preserve_terms.txt)가 출력에서 빠져도 원문을 돌려준다.
    255토큰을 넘는 입력도 원문을 돌려준다. 둘 다 fallback 으로 표시한다.
    """

    def __init__(self, artifact_dir: str):
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

    def _one(self, text, max_len=256):
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
        for step in range(min(2 * len(ids) + 16, max_len)):
            feed.update(zip(past_names, past))
            feed["input_ids"] = np.array([[out[-1]]], dtype=np.int64)
            feed["position_ids"] = np.array([[step]], dtype=np.int64)
            logits, *past = self.decoder.run(None, feed)
            nxt = int(logits[0, -1].argmax())
            if nxt == EOS:
                break
            out.append(nxt)
        return self.tok.decode(out[1:], skip_special_tokens=True).strip()
