"""Regenerate a model's parity fixtures using its current metadata decoding settings."""
import argparse
import json
from pathlib import Path

from simple_word.model import Simplifier
from training.export import PARITY_INPUTS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version")
    parser.add_argument("--models-dir", default="models")
    args = parser.parse_args()
    artifact = Path(args.models_dir) / args.version
    outputs = Simplifier(str(artifact)).simplify(PARITY_INPUTS)
    path = artifact / "parity.jsonl"
    path.write_text("".join(json.dumps({"input": src, "output": out}, ensure_ascii=False) + "\n"
                                    for src, out in zip(PARITY_INPUTS, outputs)), encoding="utf-8")
    print(f"Wrote {len(outputs)} parity cases to {path}")


if __name__ == "__main__":
    main()
