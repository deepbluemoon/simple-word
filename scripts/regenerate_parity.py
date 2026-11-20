"""Regenerate a model's parity fixtures using its current metadata decoding settings."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from simple_word.model import Simplifier, _read_metadata
from training.export import PARITY_INPUTS, _assert_parity, hf_reference_outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version")
    parser.add_argument("--models-dir", default="models")
    parser.add_argument("--hf-dir", help="HF checkpoint used for exact FP32 parity comparison")
    args = parser.parse_args()
    artifact = Path(args.models_dir) / args.version
    metadata = _read_metadata(artifact / "metadata.json")
    num_beams = metadata.get("decoding", {}).get("num_beams", 1)
    model = Simplifier(str(artifact))
    actual = model.simplify(PARITY_INPUTS)
    if metadata.get("quantization", "dynamic-int8") == "fp32":
        reference = hf_reference_outputs(args.hf_dir or artifact / "hf", PARITY_INPUTS, num_beams,
                                         model.placeholders, model.force_placeholders)
        try:
            _assert_parity(reference, actual)
        except RuntimeError as exc:
            raise SystemExit(f"{exc}; parity was not overwritten") from exc
    path = artifact / "parity.jsonl"
    path.write_text("".join(json.dumps({"input": src, "output": out}, ensure_ascii=False) + "\n"
                                    for src, out in zip(PARITY_INPUTS, actual)), encoding="utf-8")
    print(f"Wrote {len(actual)} ONNX parity cases to {path}")


if __name__ == "__main__":
    main()
