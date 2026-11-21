import io
import json
import logging
import threading
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import api.main as api_main
from api.router import ModelRouter
from api.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_request_logs(tmp_path, monkeypatch):
    monkeypatch.setattr(api_main, "LOG_DIR", tmp_path)
    monkeypatch.setattr(api_main, "router", ModelRouter(tmp_path / "models" / "registry.json"))


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
    payload = response.json()
    assert payload["request_id"]
    assert payload["term_licenses"] == api_main.difficult_term_licenses()
    assert payload == {
        "request_id": payload["request_id"],
        "model_version": "dummy",
        "term_licenses": api_main.difficult_term_licenses(),
        "sentences": [
            {"original": "첫 문장입니다.", "simple": "첫 문장입니다.", "fallback": False, "fallback_reason": None, "paragraph_id": 0, "title": False, "terms": []},
            {"original": "둘째 문장입니다!", "simple": "둘째 문장입니다!", "fallback": False, "fallback_reason": None, "paragraph_id": 0, "title": False, "terms": []},
        ],
    }


@pytest.mark.parametrize(("filename", "content_type"), [
    ("notice.pdf", "application/octet-stream"),
    ("notice.txt", "application/pdf"),
])
def test_simplify_rejects_pdf_without_reading_upload_contents(monkeypatch, filename, content_type):
    async def unexpected_read(*_args, **_kwargs):
        raise AssertionError("PDF upload contents should not be read")

    monkeypatch.setattr(api_main.UploadFile, "read", unexpected_read)
    response = client.post("/simplify", files={"file": (filename, b"ignored", content_type)})

    assert response.status_code == 415
    assert response.json()["detail"] == "PDF 파일은 지원하지 않아요. TXT, DOCX, HWPX 파일을 올려 주세요."


def zipped_file(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, value in entries.items():
            archive.writestr(name, value)
    return buffer.getvalue()


BILLION_LAUGHS = ('<!DOCTYPE lolz [<!ENTITY lol "lol">' + ''.join(
    f'<!ENTITY lol{i} "' + '&lol;' * 10 + '">' if i == 1 else
    f'<!ENTITY lol{i} "' + f'&lol{i - 1};' * 10 + '">' for i in range(1, 10)
) + ']><w:document xmlns:w="urn:w"><w:p><w:t>&lol9;</w:t></w:p></w:document>')


def test_simplify_extracts_docx_text():
    document = zipped_file({"word/document.xml": '<w:document xmlns:w="urn:w"><w:body><w:p><w:r><w:t>안내 문장입니다.</w:t></w:r></w:p></w:body></w:document>'})

    response = client.post("/simplify", files={"file": ("notice.docx", document)})

    assert response.status_code == 200
    assert response.json()["sentences"] == [{"original": "안내 문장입니다.", "simple": "안내 문장입니다.", "fallback": False,
                                             "fallback_reason": None, "paragraph_id": 0, "title": False, "terms": []}]


@pytest.mark.parametrize("filename", ["notice.txt", "application.docx", "facility.hwpx"])
def test_sample_documents_are_readable_by_simplify(filename):
    data = (Path(__file__).parents[1] / "frontend" / "public" / "samples" / filename).read_bytes()

    response = client.post("/simplify", files={"file": (filename, data)})

    assert response.status_code == 200
    sentences = response.json()["sentences"]
    assert sentences[0]["title"] is True
    assert sentences[0]["original"] == sentences[0]["simple"]
    assert len(sentences) == 4
    assert all(sentence["title"] is False for sentence in sentences[1:])


@pytest.mark.parametrize(("content", "expected_title"), [
    ("제목: 안내\n\n신청하세요.", "제목: 안내"),
    ("시설 이용 안내\n\n운영 시간은 오후 8시까지입니다.", "시설 이용 안내"),
    ("신청하세요\n\n운영 시간은 오후 8시까지입니다.", None),
    ("짧은 문장입니다.\n\n운영 시간은 오후 8시까지입니다.", None),
    ("짧은 안내", None),
])
def test_title_detection_is_limited_to_conservative_first_line(content, expected_title, monkeypatch):
    seen = []

    class Model:
        def simplify(self, sentences):
            seen.extend(sentences)
            return [f"변환: {sentence}" for sentence in sentences]

    class OneRouter:
        def select(self, request_id):
            return "v-title", "champion", Model(), None, None

    monkeypatch.setattr(api_main, "router", OneRouter())
    response = client.post("/simplify", files={"file": ("notice.txt", content)})
    sentences = response.json()["sentences"]

    assert response.status_code == 200
    if expected_title:
        assert sentences[0]["original"] == sentences[0]["simple"] == expected_title
        assert sentences[0]["title"] is True
        assert seen == [sentence["original"] for sentence in sentences[1:]]
    else:
        assert all(sentence["title"] is False for sentence in sentences)
        assert seen == [sentence["original"] for sentence in sentences]


def test_simplify_extracts_hwpx_text():
    section = '<hs:sec xmlns:hs="urn:hs" xmlns:hp="urn:hp"><hp:p><hp:run><hp:t>공고 내용입니다.</hp:t></hp:run></hp:p></hs:sec>'
    document = zipped_file({"Contents/section0.xml": section})

    response = client.post("/simplify", files={"file": ("notice.hwpx", document)})

    assert response.status_code == 200
    assert response.json()["sentences"][0]["original"] == "공고 내용입니다."


@pytest.mark.parametrize("xml", [
    '<!DOCTYPE x [<!ENTITY ext SYSTEM "file:///etc/passwd">]><w:document xmlns:w="urn:w"><w:p><w:t>&ext;</w:t></w:p></w:document>',
    BILLION_LAUGHS,
])
def test_simplify_rejects_xxe_and_entity_expansion(xml):
    response = client.post("/simplify", files={"file": ("attack.docx", zipped_file({"word/document.xml": xml}))})

    assert response.status_code == 400


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
        "request_id": "req-1", "result_id": "result-1", "sentence_index": 0,
        "model_version": "v1", "original": "원문", "simple": "쉬운 말", "vote": "up",
    })

    assert response.status_code == 200
    record = json.loads((tmp_path / "feedback.jsonl").read_text(encoding="utf-8"))
    assert record == {"request_id": "req-1", "result_id": "result-1", "sentence_index": 0,
                      "model_version": "v1", "original": "원문", "simple": "쉬운 말", "vote": "up"}


def test_feedback_redacts_known_pii_before_logging(tmp_path):
    response = client.post("/feedback", json={
        "request_id": "req-1", "result_id": "result-1", "sentence_index": 2,
        "model_version": "v1", "original": "010-1234-5678로 문의", "simple": "010-1234-5678로 연락", "vote": "up",
    })

    record = json.loads((tmp_path / "feedback.jsonl").read_text(encoding="utf-8"))
    assert response.status_code == 200
    assert record["original"] == "[전화번호]로 문의"
    assert record["simple"] == "[전화번호]로 연락"


def test_jsonl_logs_rotate_with_a_bounded_history(tmp_path, monkeypatch):
    monkeypatch.setattr(api_main, "MAX_LOG_BYTES", 60)
    monkeypatch.setattr(api_main, "MAX_LOG_BACKUPS", 2)
    monkeypatch.setattr(api_main, "MIN_LOG_FREE_BYTES", 0)

    for index in range(6):
        assert api_main.append_jsonl("feedback.jsonl", {"n": index, "value": "x" * 30}, threading.Lock())

    files = list(tmp_path.glob("feedback.jsonl*"))
    logs = [path for path in files if not path.name.endswith(".lock")]
    assert len(logs) == 3
    assert all(path.stat().st_size <= api_main.MAX_LOG_BYTES for path in logs)
    assert sum(path.stat().st_size for path in logs) <= 3 * api_main.MAX_LOG_BYTES


def test_feedback_stops_writing_when_disk_is_low(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(api_main, "MIN_LOG_FREE_BYTES", 100)
    monkeypatch.setattr(api_main.shutil, "disk_usage", lambda _: SimpleNamespace(free=0))

    with caplog.at_level(logging.WARNING):
        response = client.post("/feedback", json={
            "request_id": "req-1", "result_id": "result-1", "sentence_index": 0,
            "model_version": "v1", "original": "원문", "simple": "쉬운 말", "vote": "up",
        })

    assert response.status_code == 503
    assert not (tmp_path / "feedback.jsonl").exists()
    assert "Skipping feedback.jsonl write" in caplog.text


def test_feedback_rejects_strings_over_2000_characters():
    response = client.post("/feedback", json={
        "request_id": "req-1", "result_id": "result-1", "sentence_index": 0,
        "model_version": "v1", "original": "x" * 2001, "simple": "쉬운 말", "vote": "up",
    })

    assert response.status_code == 422


def test_feedback_requires_request_result_and_sentence_identity():
    response = client.post("/feedback", json={
        "model_version": "v1", "original": "원문", "simple": "쉬운 말", "vote": "up",
        "request_id": "req-1", "result_id": "result-1", "sentence_index": -1,
    })
    assert response.status_code == 422


def test_dockerfile_runs_non_root_and_prepares_logs():
    dockerfile = open("Dockerfile", encoding="utf-8").read()

    assert "chown app:app /app/logs" in dockerfile
    assert "USER app" in dockerfile


def test_root_and_spa_routes_serve_built_frontend(monkeypatch, tmp_path):
    from pathlib import Path

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<main>쉬운 말로 바꾸기</main>", encoding="utf-8")
    (dist / "assets").mkdir()
    (dist / "assets" / "app.js").write_text("export {}", encoding="utf-8")
    monkeypatch.setattr(api_main, "FRONTEND_DIST", dist)

    response = client.get("/")
    assert response.status_code == 200
    assert "쉬운 말로 바꾸기" in response.text
    assert client.get("/results/example").text == response.text
    assert client.get("/assets/app.js").text == "export {}"
    assert client.get("/assets/missing.js").status_code == 404


def test_request_log_marks_number_fallback_per_sentence(monkeypatch, tmp_path):
    class GuardedModel:
        def simplify_detailed(self, sentences):
            return [(s, True) if "20일" in s else (s + "!", False) for s in sentences]

    class OneRouter:
        def select(self, request_id):
            return "v-guard", "champion", GuardedModel(), None, None

    monkeypatch.setattr(api_main, "router", OneRouter())
    response = client.post("/simplify", files={"file": ("a.txt", "20일 이내 신청.\n센터에서 받는다.")})
    record = json.loads((tmp_path / "requests.jsonl").read_text().splitlines()[0])

    assert [s["simple"] for s in response.json()["sentences"]] == ["20일 이내 신청.", "센터에서 받는다.!"]
    assert [s["fallback"] for s in response.json()["sentences"]] == [True, False]
    assert [s["fallback"] for s in record["sentences"]] == [True, False]


def test_simplify_response_has_fallback_per_sentence_and_feedback_accepts_it(monkeypatch, tmp_path):
    class GuardedModel:
        def simplify_detailed(self, sentences):
            return [(s, True) if "20일" in s else (s + "!", False) for s in sentences]

    class OneRouter:
        def select(self, request_id):
            return "v-guard", "champion", GuardedModel(), None, None

    monkeypatch.setattr(api_main, "router", OneRouter())
    payload = client.post("/simplify", files={"file": ("a.txt", "20일 이내 신청.\n센터에서 받는다.")}).json()
    sentences = payload["sentences"]
    record = json.loads((tmp_path / "requests.jsonl").read_text().splitlines()[0])

    assert [s["fallback"] for s in sentences] == [True, False] == [s["fallback"] for s in record["sentences"]]
    response = client.post("/feedback", json={
        "request_id": payload["request_id"], "result_id": "result-guard", "sentence_index": 0,
        "model_version": "v-guard", **sentences[0], "vote": "down",
    })  # 웹이 문장을 통째로 보내도
    assert response.status_code == 200


def test_simplify_reports_fallback_reason_paragraph_and_terms(monkeypatch):
    class ExplainedModel:
        def simplify_explained(self, sentences):
            return [(sentence, True, "numbers") if "20일" in sentence else (sentence, False, None)
                    for sentence in sentences]

    class OneRouter:
        def select(self, request_id):
            return "v-explain", "champion", ExplainedModel(), None, None

    monkeypatch.setattr(api_main, "router", OneRouter())
    monkeypatch.setattr(api_main, "terms_in", lambda sentence: [{
        "text": "안에", "start": 4, "end": 6, "easy": ["속에"], "source": "국립국어원_15130006",
    }] if "안에" in sentence else [])
    response = client.post("/simplify", files={"file": ("notice.txt", "20일 안에 신청.\n\n다음 문단은 확인합니다.")})

    assert response.json()["sentences"] == [
        {"original": "20일 안에 신청.", "simple": "20일 안에 신청.", "fallback": True,
         "fallback_reason": "numbers", "paragraph_id": 0, "title": False,
         "terms": [{"text": "안에", "start": 4, "end": 6, "easy": ["속에"], "source": "국립국어원_15130006"}]},
        {"original": "다음 문단은 확인합니다.", "simple": "다음 문단은 확인합니다.", "fallback": False,
         "fallback_reason": None, "paragraph_id": 1, "title": False, "terms": []},
    ]
