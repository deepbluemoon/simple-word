import hashlib
import json
import threading
from pathlib import Path

from simple_word.model import Simplifier


class ModelRouter:
    def __init__(self, registry_path: str | Path):
        self.registry_path = Path(registry_path)
        self.models_dir = self.registry_path.parent
        self.lock = threading.RLock()
        self.signature = object()
        self.models: dict[str, Simplifier] = {}
        self.registry: dict = {}
        self.reload_if_changed()

    @staticmethod
    def _valid_version(version) -> bool:
        return isinstance(version, str) and version not in {"", ".", ".."} and "/" not in version and "\\" not in version

    def reload_if_changed(self) -> None:
        try:
            stat = self.registry_path.stat()
            signature = (stat.st_mtime_ns, stat.st_size)
            data = json.loads(self.registry_path.read_text(encoding="utf-8"))
            champion = data["champion"]
            canary = data.get("canary")
            shadow = data.get("shadow")
            weight = data.get("canary_weight", 0)
            if not self._valid_version(champion) or any(
                value is not None and not self._valid_version(value) for value in (canary, shadow)
            ):
                return
            if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not 0 <= weight <= 1:
                return
            registry = {"champion": champion, "canary": canary, "canary_weight": weight, "shadow": shadow}
        except FileNotFoundError:
            signature = None
            registry = {"champion": "dummy", "canary": None, "canary_weight": 0, "shadow": None}
        except (OSError, ValueError, KeyError, TypeError):
            return

        with self.lock:
            if signature == self.signature:
                return
            versions = {v for v in (registry["champion"], registry["canary"], registry["shadow"]) if v}
            try:
                models = {
                    version: self.models.get(version) or Simplifier(str(self.models_dir / version))
                    for version in versions
                }
            except Exception:
                return
            self.registry = registry
            self.models = models
            self.signature = signature

    def select(self, request_id: str):
        self.reload_if_changed()
        with self.lock:
            registry, models = self.registry, self.models
            role = "champion"
            version = registry["champion"]
            canary = registry["canary"]
            fraction = int.from_bytes(hashlib.sha256(request_id.encode()).digest(), "big") / 2**256
            if canary and fraction < registry["canary_weight"]:
                role, version = "canary", canary
            shadow = registry["shadow"]
            return version, role, models[version], shadow, models.get(shadow)

    def health(self) -> dict[str, list[dict[str, list[str] | str]]]:
        self.reload_if_changed()
        with self.lock:
            roles: dict[str, list[str]] = {}
            for role in ("champion", "canary", "shadow"):
                version = self.registry.get(role)
                if version:
                    roles.setdefault(version, []).append(role)
            return {"model_versions": [{"version": version, "roles": version_roles} for version, version_roles in roles.items()]}
