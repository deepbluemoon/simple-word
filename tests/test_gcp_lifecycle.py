import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_merge_lifecycle_preserves_unmanaged_rules_and_replaces_managed_rule(tmp_path):
    current = {
        "lifecycle": {
            "rule": [
                {"action": {"type": "Delete"}, "condition": {"age": 7, "matchesPrefix": ["staging/"]}},
                {"action": {"type": "SetStorageClass", "storageClass": "NEARLINE"}, "condition": {"age": 30}},
            ]
        }
    }
    managed = json.loads((ROOT / "deploy/gcp/lifecycle.json").read_text())
    current_path, managed_path, output_path = (tmp_path / name for name in ("current.json", "managed.json", "output.json"))
    current_path.write_text(json.dumps(current))
    managed_path.write_text(json.dumps(managed))

    subprocess.run(
        [sys.executable, str(ROOT / "deploy/gcp/merge_lifecycle.py"), str(current_path), str(managed_path), str(output_path)],
        check=True,
    )

    rules = json.loads(output_path.read_text())["rule"]
    assert len(rules) == 2
    assert rules[0]["action"]["type"] == "SetStorageClass"
    assert rules[1] == managed["rule"][0]
