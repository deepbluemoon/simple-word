import argparse
import json
import sys
from pathlib import Path

from simple_word.model import Simplifier


def check_parity(version: str, models_dir: str | Path = "models") -> list[str]:
    artifact = Path(models_dir) / version
    path = artifact / "parity.jsonl"
    errors = []
    if not path.is_file():
        return [f"Missing {path}"]
    try:
        model = Simplifier(str(artifact))
    except Exception as exc:
        return [f"Could not load model {version}: {exc}"]
    count = 0
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            record = json.loads(line)
            inputs = record["input"]
            expected = record["output"]
            inputs = [inputs] if isinstance(inputs, str) else inputs
            expected = [expected] if isinstance(expected, str) else expected
            if not isinstance(inputs, list) or not all(isinstance(item, str) for item in inputs):
                raise ValueError("input must be a string or list of strings")
            if not isinstance(expected, list) or not all(isinstance(item, str) for item in expected):
                raise ValueError("output must be a string or list of strings")
            count += 1
            actual = model.simplify(inputs)
            if actual != expected:
                errors.append(f"line {line_number}: expected {expected!r}, got {actual!r}")
        except Exception as exc:
            errors.append(f"line {line_number}: invalid parity record: {exc}")
    if count == 0:
        errors.append("parity.jsonl has no valid records")
    return errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check model parity fixtures")
    parser.add_argument("version")
    parser.add_argument("--models-dir", default="models")
    args = parser.parse_args(argv)
    errors = check_parity(args.version, args.models_dir)
    if errors:
        print("FAIL")
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"PASS parity: {args.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
