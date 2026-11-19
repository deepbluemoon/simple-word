import io
import json
import threading
import zipfile

import pytest
from pypdf import PdfWriter
from fastapi.testclient import TestClient

import api.main as api_main
from api.router import ModelRouter
from api.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_request_logs(tmp_path, monkeypatch):
    monkeypatch.setattr(api_main, "LOG_DIR", tmp_path)


def test_health_reports_loaded_model_version():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"model_versions": [{"version": "dummy", "roles": ["champion"]}]}


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


def zipped_file(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, value in entries.items():
            archive.writestr(name, value)
    return buffer.getvalue()


def test_simplify_extracts_docx_text():
    document = zipped_file({"word/document.xml": '<w:document xmlns:w="urn:w"><w:body><w:p><w:r><w:t>안내 문장입니다.</w:t></w:r></w:p></w:body></w:document>'})

    response = client.post("/simplify", files={"file": ("notice.docx", document)})

    assert response.status_code == 200
    assert response.json()["sentences"] == [{"original": "안내 문장입니다.", "simple": "안내 문장입니다."}]


def test_simplify_extracts_hwpx_text():
    section = '<hs:sec xmlns:hs="urn:hs" xmlns:hp="urn:hp"><hp:p><hp:run><hp:t>공고 내용입니다.</hp:t></hp:run></hp:p></hs:sec>'
    document = zipped_file({"Contents/section0.xml": section})

    response = client.post("/simplify", files={"file": ("notice.hwpx", document)})

    assert response.status_code == 200
    assert response.json()["sentences"][0]["original"] == "공고 내용입니다."


def test_simplify_accepts_valid_pdf():
    buffer = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(buffer)

    response = client.post("/simplify", files={"file": ("notice.pdf", buffer.getvalue())})

    assert response.status_code == 200


def test_simplify_rejects_empty_and_oversized_files():
    empty = client.post("/simplify", files={"file": ("empty.txt", b"")})
    oversized = client.post("/simplify", files={"file": ("large.txt", b"a" * (5 * 1024 * 1024 + 1))})

    assert empty.status_code == 400
    assert "empty" in empty.json()["detail"].lower()
    assert oversized.status_code == 400
    assert "5 mb" in oversized.json()["detail"].lower()


def test_simplify_rejects_zip_with_large_unpacked_size(monkeypatch):
    document = zipped_file({"word/document.xml": "tiny"})
    original_getinfo = zipfile.ZipFile.getinfo

    def report_large_size(archive, name):
        info = original_getinfo(archive, name)
        if name == "word/document.xml":
            info.file_size = 20 * 1024 * 1024 + 1
        return info

    monkeypatch.setattr(zipfile.ZipFile, "getinfo", report_large_size)
    response = client.post("/simplify", files={"file": ("bomb.docx", document)})

    assert response.status_code == 400
    assert "unpacked" in response.json()["detail"].lower()


def test_simplify_rejects_pdf_over_page_limit():
    buffer = io.BytesIO()
    writer = PdfWriter()
    for _ in range(51):
        writer.add_blank_page(width=200, height=200)
    writer.write(buffer)

    response = client.post("/simplify", files={"file": ("many.pdf", buffer.getvalue())})

    assert response.status_code == 400
    assert "50-page" in response.json()["detail"]


def test_simplify_rejects_more_than_100_sentences():
    content = "\n".join(["문장"] * 101)

    response = client.post("/simplify", files={"file": ("many.txt", content)})

    assert response.status_code == 400
    assert "100-sentence" in response.json()["detail"]


def test_simplify_sentence_limit_can_be_configured(monkeypatch):
    import api.main as api_main

    monkeypatch.setattr(api_main, "MAX_SENTENCES", 1)
    response = client.post("/simplify", files={"file": ("many.txt", "하나\n둘")})

    assert response.status_code == 400
    assert response.json() == {"detail": "Document exceeds 1-sentence limit"}


def test_simplify_runs_extraction_and_model_in_threadpool(monkeypatch):
    event_loop_threads = []
    worker_threads = []
    original_run_in_threadpool = api_main.run_in_threadpool

    def record_worker(filename, data, request_id):
        worker_threads.append(threading.get_ident())
        return api_main.simplify_content(filename, data, request_id)

    async def track_threadpool(func, *args):
        event_loop_threads.append(threading.get_ident())
        return await original_run_in_threadpool(record_worker, *args)

    monkeypatch.setattr(api_main, "run_in_threadpool", track_threadpool)
    response = client.post("/simplify", files={"file": ("short.txt", "text")})

    assert response.status_code == 200
    assert worker_threads and worker_threads[0] != event_loop_threads[0]


def test_simplify_returns_429_and_retry_after_when_at_capacity():
    assert api_main.SIMPLIFY_SLOTS.acquire(blocking=False)
    assert api_main.SIMPLIFY_SLOTS.acquire(blocking=False)
    try:
        response = client.post("/simplify", files={"file": ("short.txt", "text")})
    finally:
        api_main.SIMPLIFY_SLOTS.release()
        api_main.SIMPLIFY_SLOTS.release()

    assert response.status_code == 429
    assert response.headers["retry-after"] == "1"


def test_router_shadow_logs_selected_versions_and_redacts_pii(tmp_path, monkeypatch):
    registry = tmp_path / "models" / "registry.json"
    registry.parent.mkdir()
    for version in ("v1", "v2", "v3"):
        artifact = registry.parent / version
        artifact.mkdir()
        (artifact / "metadata.json").touch()
    registry.write_text(json.dumps({
        "champion": "v1", "canary": "v2", "canary_weight": 1, "shadow": "v3",
    }))
    monkeypatch.setattr(api_main, "router", ModelRouter(registry))
    text = "전화 010-1234-5678, 메일 a.person@example.org, 주민 900101-1234567"

    response = client.post("/simplify", files={"file": ("pii.txt", text)})
    records = [json.loads(line) for line in (tmp_path / "requests.jsonl").read_text().splitlines()]

    assert response.json()["model_version"] == "v2"
    assert {record["role"] for record in records} == {"canary", "shadow"}
    assert all(record["request_id"] == records[0]["request_id"] for record in records)
    assert all({"timestamp", "model_version", "sentence_count", "latency_ms", "sentences"} <= record.keys() for record in records)
    serialized = json.dumps(records, ensure_ascii=False)
    assert "[전화번호]" in serialized and "[이메일]" in serialized and "[주민번호]" in serialized
    assert "010-1234-5678" not in serialized and "a.person@example.org" not in serialized


def test_inference_error_returns_500_logs_role_and_releases_slot(monkeypatch, tmp_path):
    class BrokenModel:
        def simplify(self, sentences):
            raise RuntimeError("inference failed")

    class BrokenRouter:
        def select(self, request_id):
            return "v-broken", "canary", BrokenModel(), None, None

    monkeypatch.setattr(api_main, "router", BrokenRouter())
    monkeypatch.setattr(api_main, "SIMPLIFY_SLOTS", threading.BoundedSemaphore(1))

    response = client.post("/simplify", files={"file": ("fail.txt", "입력 문장")})
    record = json.loads((tmp_path / "requests.jsonl").read_text().splitlines()[0])

    assert response.status_code == 500
    assert record["role"] == "canary" and record["model_version"] == "v-broken"
    assert record["error"] == "RuntimeError"
    assert api_main.SIMPLIFY_SLOTS.acquire(blocking=False)
    api_main.SIMPLIFY_SLOTS.release()


def test_busy_shadow_is_skipped_and_logged(monkeypatch, tmp_path):
    class MustNotRun:
        def simplify(self, sentences):
            raise AssertionError("busy shadow should not run")

    shadow_slots = threading.BoundedSemaphore(1)
    shadow_slots.acquire()
    monkeypatch.setattr(api_main, "SHADOW_SLOTS", shadow_slots)
    try:
        api_main.run_shadow("request-1", "v-shadow", MustNotRun(), ["문장"])
    finally:
        shadow_slots.release()

    record = json.loads((tmp_path / "requests.jsonl").read_text().splitlines()[0])
    assert record["role"] == "shadow" and record["model_version"] == "v-shadow"
    assert record["error"] == "shadow_busy"


def test_main_slot_is_released_even_if_background_task_never_runs(tmp_path, monkeypatch):
    registry = tmp_path / "models" / "registry.json"
    registry.parent.mkdir()
    artifact = registry.parent / "v-shadow"
    artifact.mkdir()
    (artifact / "metadata.json").touch()
    registry.write_text(json.dumps({"champion": "dummy", "shadow": "v-shadow"}))
    monkeypatch.setattr(api_main, "router", ModelRouter(registry))
    slots = threading.BoundedSemaphore(1)
    monkeypatch.setattr(api_main, "SIMPLIFY_SLOTS", slots)
    monkeypatch.setattr("fastapi.BackgroundTasks.add_task", lambda *args, **kwargs: None)

    response = client.post("/simplify", files={"file": ("notice.txt", "한 문장")})

    assert response.status_code == 200
    assert slots.acquire(blocking=False)
    slots.release()


def test_feedback_appends_jsonl(tmp_path, monkeypatch):
    monkeypatch.setattr("api.main.LOG_DIR", tmp_path)

    response = client.post("/feedback", json={
        "model_version": "v1", "original": "원문", "simple": "쉬운 말", "vote": "up",
    })

    assert response.status_code == 200
    assert (tmp_path / "feedback.jsonl").read_text(encoding="utf-8") == '{"model_version": "v1", "original": "원문", "simple": "쉬운 말", "vote": "up"}\n'


def test_feedback_rejects_strings_over_2000_characters():
    response = client.post("/feedback", json={
        "model_version": "v1", "original": "x" * 2001, "simple": "쉬운 말", "vote": "up",
    })

    assert response.status_code == 422


def test_dockerfile_runs_non_root_and_prepares_logs():
    dockerfile = open("Dockerfile", encoding="utf-8").read()

    assert "chown app:app /app/logs" in dockerfile
    assert "USER app" in dockerfile


def test_root_serves_upload_page():
    response = client.get("/")

    assert response.status_code == 200
    assert "쉬운 말로 바꾸기" in response.text
