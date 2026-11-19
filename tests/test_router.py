import json
import logging

import api.router as router_module
from api.router import ModelRouter


def add_artifact(models_dir, version):
    artifact = models_dir / version
    artifact.mkdir(parents=True, exist_ok=True)
    (artifact / "metadata.json").touch()


def test_router_falls_back_to_one_dummy_model_without_registry(tmp_path):
    router = ModelRouter(tmp_path / "registry.json")

    assert router.health() == {"model_versions": [{"version": "dummy", "roles": ["champion"]}]}
    assert router.select("request-1")[0:2] == ("dummy", "champion")


def test_registry_reload_updates_roles_and_drops_old_models(tmp_path):
    path = tmp_path / "registry.json"
    for version in ("v1", "v2", "v3", "champion-v4"):
        add_artifact(tmp_path, version)
    path.write_text(json.dumps({"champion": "v1", "canary": "v2", "canary_weight": 0.2, "shadow": "v3"}))
    router = ModelRouter(path)
    first = router.health()
    assert [item["version"] for item in first["model_versions"]] == ["v1", "v2", "v3"]

    path.write_text(json.dumps({"champion": "champion-v4", "canary": None, "canary_weight": 0, "shadow": None}))
    second = router.health()

    assert second == {"model_versions": [{"version": "champion-v4", "roles": ["champion"]}]}
    assert set(router.models) == {"champion-v4"}


def test_canary_weight_uses_stable_request_id_hash(tmp_path):
    path = tmp_path / "registry.json"
    add_artifact(tmp_path, "v1")
    add_artifact(tmp_path, "v2")
    path.write_text(json.dumps({"champion": "v1", "canary": "v2", "canary_weight": 0.25, "shadow": None}))
    router = ModelRouter(path)
    selections = [router.select(f"request-{i}")[1] for i in range(1000)]
    canary_fraction = selections.count("canary") / len(selections)

    assert router.select("same-request")[1] == router.select("same-request")[1]
    assert 0.20 <= canary_fraction <= 0.30


def test_registry_rejects_missing_artifacts_and_warns_on_load_failure(tmp_path, monkeypatch, caplog):
    path = tmp_path / "registry.json"
    good_artifact = tmp_path / "v1"
    good_artifact.mkdir()
    (good_artifact / "metadata.json").write_text("{}")
    path.write_text(json.dumps({"champion": "v1"}))
    router = ModelRouter(path)

    failed_artifact = tmp_path / "v2"
    failed_artifact.mkdir()
    (failed_artifact / "encoder.onnx").touch()
    original_simplifier = router_module.Simplifier

    def broken_simplifier(artifact_dir):
        if artifact_dir.endswith("/v2"):
            raise RuntimeError("bad model")
        return original_simplifier(artifact_dir)

    monkeypatch.setattr(router_module, "Simplifier", broken_simplifier)
    caplog.set_level(logging.WARNING)
    path.write_text(json.dumps({"champion": "v2"}))
    router.health()
    assert "Could not load model registry" in caplog.text
    assert set(router.models) == {"v1"}

    path.write_text(json.dumps({"champion": "typo"}))
    router.health()
    assert "has no metadata.json or encoder.onnx" in caplog.text
    assert set(router.models) == {"v1"}

    path.write_text(json.dumps({"champion": "dummy"}))
    assert router.health() == {"model_versions": [{"version": "dummy", "roles": ["champion"]}]}
