from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_health_reports_loaded_model_version():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"model_versions": ["dummy"]}


def test_simplify_txt_returns_original_and_simple_sentences():
    response = client.post(
        "/simplify",
        files={"file": ("notice.txt", "첫 문장입니다.\n둘째 문장입니다!", "text/plain")},
    )

    assert response.status_code == 200
    assert response.json() == {
        "model_version": "dummy",
        "sentences": [
            {"original": "첫 문장입니다.", "simple": "첫 문장입니다."},
            {"original": "둘째 문장입니다!", "simple": "둘째 문장입니다!"},
        ],
    }


def test_simplify_rejects_non_txt_file():
    response = client.post("/simplify", files={"file": ("notice.pdf", b"data")})

    assert response.status_code == 400
