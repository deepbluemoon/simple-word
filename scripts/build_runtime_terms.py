"""Build the attributed runtime dictionary from locally stored licensed sources."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from training.terms import difficult_terms


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, default=Path("simple_word/difficult_terms.json"))
    args = parser.parse_args()
    payload = {
        "licenses": {
            "국립국어원_15130006": "국립국어원 공공언어 평가용 용어 목록 · 공공누리 제1유형(출처표시)",
            "법제처_법령정보지식베이스": "법제처 법령용어-일상용어 연계 · 이용허락범위 제한 없음",
        },
        "source_url": "https://www.data.go.kr/data/15130006/fileData.do",
        "terms": difficult_terms(args.data_dir),
    }
    args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{len(payload['terms'])} terms → {args.output}")


if __name__ == "__main__":
    main()
