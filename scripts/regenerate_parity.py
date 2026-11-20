"""Regenerate a model's parity fixtures using its current metadata decoding settings."""
import argparse
import json
import sys
from pathlib import Path

# `python scripts/regenerate_parity.py`로 돌리면 sys.path[0]이 scripts/라서, 설치된 다른 체크아웃의 simple_word를
# 불러올 수 있다(옛 숫자 검사로 parity를 만들어 게이트가 깨짐). 이 저장소 루트를 먼저 본다.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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
