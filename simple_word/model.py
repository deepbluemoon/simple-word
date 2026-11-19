from pathlib import Path

EOS = 1  # KoBART: bos = eos = decoder_start = 1


class Simplifier:
    """models/<version>/ 의 ONNX(INT8)를 onnxruntime(CPU)으로 불러 탐욕 디코딩(결정적, self-attention KV 캐시).

    artifact_dir 에 encoder.onnx 가 없을 때만 입력을 그대로 돌려주는 더미로 동작한다.
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
        if self.dummy:
            return list(sentences)
        return [self._one(s) for s in sentences]

    def _one(self, text, max_len=256):
        import numpy as np

        ids = self.tok.encode(text, add_special_tokens=False).ids[: max_len - 1] + [EOS]
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
