#!/usr/bin/env python3
"""Merge the service-managed staging cleanup rule into a bucket lifecycle."""

import json
import sys
from pathlib import Path


def merge(current: dict, managed: dict) -> dict:
    lifecycle = current.get("lifecycle", {})
    rules = lifecycle.get("rule", []) if isinstance(lifecycle, dict) else []
    managed_rules = managed.get("rule", [])
    rules = [rule for rule in rules if not _is_managed(rule)]
    return {"rule": rules + managed_rules}


def _is_managed(rule: dict) -> bool:
    condition = rule.get("condition", {})
    return (
        rule.get("action", {}).get("type") == "Delete"
        and condition.get("matchesPrefix") == ["staging/"]
    )


if __name__ == "__main__":
    current_path, managed_path, output_path = map(Path, sys.argv[1:4])
    current = json.loads(current_path.read_text(encoding="utf-8"))
    managed = json.loads(managed_path.read_text(encoding="utf-8"))
    output_path.write_text(json.dumps(merge(current, managed)), encoding="utf-8")
