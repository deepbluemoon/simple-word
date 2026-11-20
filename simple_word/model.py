import json
from pathlib import Path

from simple_word.numbers import numbers
from simple_word.placeholders import TOKENS as PH_TOKENS, mask, unmask
from simple_word.terms import missing_terms, preserve_terms

EOS = 1  # KoBART: bos = eos = decoder_start = 1
LENGTH_PENALTY = 1.0


def _read_metadata(path):
    try:
        metadata = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        metadata = {}
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} must contain valid JSON metadata") from exc
    if not isinstance(metadata, dict):
        raise ValueError("metadata.json must be a JSON object")
    decoding = metadata.get("decoding", {})
    if not isinstance(decoding, dict):
        raise ValueError("metadata decoding must be a JSON object")
    num_beams = decoding.get("num_beams", 1)
    if type(num_beams) is not int or num_beams < 1:
        raise ValueError("metadata decoding.num_beams must be an integer of at least 1")
    return metadata


class Simplifier:
    """models/<version>/ 의 ONNX(INT8)를 onnxruntime(CPU)으로 불러 결정적 디코딩(self-attention KV 캐시).

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
        metadata = _read_metadata(self.artifact_dir / "metadata.json")
        self.num_beams = metadata.get("decoding", {}).get("num_beams", 1)
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
            force_placeholders = bool(metadata.get("decoding", {}).get("force_placeholders"))
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
                candidates = self._candidates(masked, slots, getattr(self, "force_placeholders", False))
            else:
                candidates = self._candidates(s)
            reason = None
            for candidate in candidates:
                if candidate is None:
                    reason = reason or "length"
                    continue
                y = unmask(candidate, slots) if getattr(self, "placeholders", False) else candidate
                if y is None:
                    reason = reason or "placeholder"
                elif not y or len(y) * 2 < len(s):
                    reason = reason or "length"
                elif numbers(y) != numbers(s):
                    reason = reason or "numbers"
                elif missing_terms(s, y, preserve_terms()):
                    reason = reason or "preserve"
                else:
                    out.append((y, False, None))
                    break
            else:
                out.append((s, True, reason or "length"))
        return out

    def _candidates(self, text, slots=None, force=False):
        return self._beam(text, slots, force)

    def _beam(self, text, slots=None, force=False, max_len=256):
        """폭 1은 greedy, 넓은 폭은 배치 beam search로 안전 후보를 점수 순 반환한다."""
        import numpy as np

        ids = self.tok.encode(text, add_special_tokens=False).ids
        if len(ids) > max_len - 1:
            return [None]
        ids = ids + [EOS]
        x = np.array([ids], dtype=np.int64)
        mask = np.ones_like(x)
        cross = self.encoder.run(None, {"input_ids": x, "attention_mask": mask})
        heads, hd = cross[0].shape[1], cross[0].shape[3]
        past_names = [i.name for i in self.decoder.get_inputs() if i.name.startswith("past_")]
        need, banned = set(), []
        if slots is not None:
            ph = {t: self.tok.token_to_id(t) for t in PH_TOKENS}
            need = {ph[t] for t in slots}
            banned = [i for t, i in ph.items() if t not in slots and i is not None]
        beams = [([EOS], 0.0, [])]
        finished = []
        width = getattr(self, "num_beams", 1)
        steps = min(2 * len(ids) + 16, max_len)
        for step in range(steps):
            batch = len(beams)
            feed = {"attention_mask": np.repeat(mask, batch, axis=0)}
            feed.update((output.name, np.repeat(value, batch, axis=0))
                        for output, value in zip(self.encoder.get_outputs(), cross))
            if past_names:
                past = [np.concatenate([beam[2][index] for beam in beams], axis=0)
                        if beams[0][2] else np.zeros((batch, heads, 0, hd), dtype=np.float32)
                        for index in range(len(past_names))]
                feed.update(zip(past_names, past))
            feed["input_ids"] = np.array([[beam[0][-1]] for beam in beams], dtype=np.int64)
            feed["position_ids"] = np.full((batch, 1), step, dtype=np.int64)
            logits, *next_past = self.decoder.run(None, feed)
            log_probs = logits[:, -1, :].astype(np.float64)
            log_probs -= np.logaddexp.reduce(log_probs, axis=1, keepdims=True)
            candidates = []
            for parent, (tokens, score, _) in enumerate(beams):
                row = log_probs[parent].copy()
                if slots is not None:
                    row[banned] = -np.inf
                    if force and need - set(tokens):
                        row[EOS] = -np.inf
                count = min(width, np.isfinite(row).sum())
                if not count:
                    continue
                cutoff = np.partition(row, -count)[-count]
                token_ids = np.flatnonzero(row > cutoff)
                ties = np.flatnonzero(row == cutoff)[:count - len(token_ids)]
                token_ids = np.concatenate((token_ids, ties))
                for token in token_ids:
                    candidates.append((score + float(row[token]), parent, int(token)))
            candidates.sort(key=lambda item: (-item[0], item[2], item[1]))
            next_beams = []
            for score, parent, token in candidates:
                tokens = beams[parent][0] + [token]
                if token == EOS:
                    finished.append((tokens, score))
                    finished.sort(key=lambda item: (-self._normalized_score(item[1], item[0]), item[0]))
                    del finished[width:]
                elif len(next_beams) < width:
                    next_beams.append((tokens, score, [value[parent:parent + 1] for value in next_past]))
            beams = next_beams
            if not beams:
                break
            if len(finished) == width and self._normalized_score(finished[-1][1], finished[-1][0]) >= max(
                self._normalized_score(beam[1], beam[0]) for beam in beams
            ):
                break
        ranked = finished + [(tokens, score) for tokens, score, _ in beams]
        ranked.sort(key=lambda item: (-self._normalized_score(item[1], item[0]), item[0]))
        return [self.tok.decode(tokens[1:], skip_special_tokens=True).strip() for tokens, _ in ranked[:width]]

    @staticmethod
    def _normalized_score(score, tokens):
        return score / max(1, len(tokens) - 1) ** LENGTH_PENALTY
