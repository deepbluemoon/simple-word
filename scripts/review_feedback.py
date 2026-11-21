"""Print one latest feedback record per request/result/sentence key."""
import argparse
import json
from pathlib import Path


def latest_feedback(records):
    latest = {}
    for index, record in enumerate(records):
        request_id = record.get("request_id")
        result_id = record.get("result_id")
        sentence_index = record.get("sentence_index")
        key = (request_id, result_id, sentence_index) if (
            isinstance(request_id, str) and request_id
            and isinstance(result_id, str) and result_id
            and isinstance(sentence_index, int) and not isinstance(sentence_index, bool)
        ) else ("legacy", index)
        latest[key] = (index, record)
    return [record for _, record in sorted(latest.values())]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path, default=Path("logs/feedback.jsonl"))
    args = parser.parse_args()
    records = []
    with args.path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                parser.error(f"{args.path}:{line_number}: invalid JSON: {exc.msg}")
            if not isinstance(record, dict):
                parser.error(f"{args.path}:{line_number}: expected a JSON object")
            records.append(record)
    for record in latest_feedback(records):
        print(json.dumps(record, ensure_ascii=False))


if __name__ == "__main__":
    main()
