import json

from api.router import ModelRouter


def test_router_falls_back_to_one_dummy_model_without_registry(tmp_path):
    router = ModelRouter(tmp_path / "registry.json")

    assert router.health() == {"model_versions": [{"version": "dummy", "roles": ["champion"]}]}
    assert router.select("request-1")[0:2] == ("dummy", "champion")


def test_registry_reload_updates_roles_and_drops_old_models(tmp_path):
    path = tmp_path / "registry.json"
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
    path.write_text(json.dumps({"champion": "v1", "canary": "v2", "canary_weight": 0.25, "shadow": None}))
    router = ModelRouter(path)
    selections = [router.select(f"request-{i}")[1] for i in range(1000)]
    canary_fraction = selections.count("canary") / len(selections)

    assert router.select("same-request")[1] == router.select("same-request")[1]
    assert 0.20 <= canary_fraction <= 0.30
