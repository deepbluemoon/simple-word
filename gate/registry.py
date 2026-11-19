"""models/registry.json 읽기·쓰기. 게이트를 통과한 새 버전을 canary 후보로 적는 데까지만 한다.

실제 버킷 업로드, GCP Cloud Run 카나리·섀도 배포, Lightsail 롤링 교체는 배포 단계(deploy/)가 맡는다.
후보는 canary_weight 0으로 적어 두므로 이 파일을 그대로 서빙해도 트래픽은 champion에만 간다.
"""
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

DEFAULT = {"champion": "dummy", "canary": None, "canary_weight": 0, "shadow": None}


def read_registry(path="models/registry.json") -> dict:
    path = Path(path)
    if not path.is_file():
        return dict(DEFAULT)
    return {**DEFAULT, **json.loads(path.read_text(encoding="utf-8"))}


def write_registry(registry: dict, path="models/registry.json") -> None:
    """임시 파일에 쓴 뒤 바꿔치기 — 라우터가 반쯤 쓰인 파일을 읽지 않게."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".registry-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.replace(tmp, path)


def register_candidate(version: str, gate_result: dict, path="models/registry.json") -> dict:
    """게이트 통과 버전을 canary 후보(weight 0)로 적는다. champion·shadow는 건드리지 않는다.

    같은 버전으로 다시 부르면 registry는 그대로다(다시 돌려도 같은 결과).
    """
    if not gate_result.get("passed") or gate_result.get("candidate") != version:
        raise ValueError(f"{version}: 게이트를 통과한 버전만 후보로 등록한다 ({gate_result.get('reasons')})")
    registry = read_registry(path)
    if version == registry["champion"]:
        raise ValueError(f"{version}은 이미 champion이다")
    if registry.get("candidate", {}).get("version") == version and registry["canary"] == version:
        return registry
    registry["canary"] = version
    registry["canary_weight"] = 0
    registry["candidate"] = {
        "version": version,
        "status": "pending_canary",  # 배포 단계가 GCP 카나리·섀도 검증 후 바꾼다
        "registered_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "gate": {"champion": gate_result.get("champion"), "evaluated_at": gate_result.get("evaluated_at")},
    }
    write_registry(registry, path)
    return registry
