import io
import json
import os
import re
import threading
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from xml.etree import ElementTree

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from starlette.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from api.router import ModelRouter

app = FastAPI()
LOG_DIR = Path(os.getenv("LOG_DIR", "./logs"))
router = ModelRouter(os.getenv("REGISTRY_PATH", "models/registry.json"))
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_UNPACKED_BYTES = 20 * 1024 * 1024
MAX_PDF_PAGES = 50
# shortcut: tune after measuring Lightsail p95 (#6).
MAX_SENTENCES = int(os.getenv("MAX_SENTENCES", "100"))
SIMPLIFY_SLOTS = threading.BoundedSemaphore(int(os.getenv("MAX_CONCURRENT_SIMPLIFY", "2")))
SHADOW_SLOTS = threading.BoundedSemaphore(1)
feedback_lock = threading.Lock()
request_log_lock = threading.Lock()
PII_PATTERNS = (
    (re.compile(r"\b\d{6}[- ]?[1-8]\d{6}\b"), "[주민번호]"),
    (re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"), "[이메일]"),
    (re.compile(r"(?<!\d)(?:\+?82[- ]?)?(?:0\d{1,2}|10)[- ]?\d{3,4}[- ]?\d{4}(?!\d)"), "[전화번호]"),
)


class Feedback(BaseModel):
    model_version: str = Field(max_length=2000)
    original: str = Field(max_length=2000)
    simple: str = Field(max_length=2000)
    vote: Literal["up", "down"]


def xml_paragraph_text(data: bytes) -> str:
    root = ElementTree.fromstring(data)
    paragraphs = []
    for paragraph in root.iter():
        if paragraph.tag.rsplit("}", 1)[-1] == "p":
            text = "".join(
                node.text or ""
                for node in paragraph.iter()
                if node.tag.rsplit("}", 1)[-1] == "t"
            )
            if text.strip():
                paragraphs.append(text)
    return "\n".join(paragraphs)


def extract_text(filename: str, data: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    try:
        if suffix == ".txt":
            return data.decode("utf-8")
        if suffix in {".docx", ".hwpx"}:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if sum(archive.getinfo(name).file_size for name in archive.namelist()) > MAX_UNPACKED_BYTES:
                    raise HTTPException(status_code=400, detail="Unpacked document exceeds 20 MB limit")
                if suffix == ".docx":
                    return xml_paragraph_text(archive.read("word/document.xml"))
                sections = sorted(
                    name for name in archive.namelist()
                    if name.startswith("Contents/section") and name.endswith(".xml")
                )
                if not sections:
                    raise ValueError("HWPX contains no document sections")
                return "\n".join(xml_paragraph_text(archive.read(name)) for name in sections)
        if suffix == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            if len(reader.pages) > MAX_PDF_PAGES:
                raise HTTPException(status_code=400, detail="PDF exceeds 50-page limit")
            return "\n".join(page.extract_text() or "" for page in reader.pages)
    except HTTPException:
        raise
    except (UnicodeDecodeError, zipfile.BadZipFile, KeyError, ElementTree.ParseError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid {suffix[1:].upper()} file: {exc}") from exc
    except Exception as exc:
        if suffix == ".pdf":
            raise HTTPException(status_code=400, detail=f"Invalid PDF file: {exc}") from exc
        raise
    raise HTTPException(status_code=400, detail="Supported files: .txt, .docx, .hwpx, .pdf")


@app.get("/health")
def health() -> dict:
    return router.health()


def redact(text: str) -> str:
    for pattern, replacement in PII_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def log_request(
    request_id: str,
    role: str,
    version: str,
    sentences: list[str],
    outputs: list[str],
    started: float,
    error: str | None = None,
    fallbacks: list[bool] | None = None,
) -> None:
    record = {
        "request_id": request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "role": role,
        "model_version": version,
        "sentence_count": len(sentences),
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        "sentences": [
            {"original": redact(original), "simple": redact(simple), "fallback": fallback}
            for original, simple, fallback in zip(sentences, outputs, fallbacks or [False] * len(outputs))
        ],
    }
    if error:
        record["error"] = error
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with request_log_lock, (LOG_DIR / "requests.jsonl").open("a", encoding="utf-8") as log:
        log.write(json.dumps(record, ensure_ascii=False) + "\n")


def run_model(model, sentences: list[str]) -> tuple[list[str], list[bool]]:
    """(출력, 문장별 숫자 안전장치 fallback 여부). simplify_detailed 가 없는 모델은 fallback 없음으로 본다."""
    detailed = getattr(model, "simplify_detailed", None)
    if detailed is None:
        outputs = model.simplify(sentences)
        return outputs, [False] * len(outputs)
    pairs = detailed(sentences)
    return [text for text, _ in pairs], [fallback for _, fallback in pairs]


def simplify_content(filename: str, data: bytes, request_id: str):
    started = time.perf_counter()
    version, role, model, shadow_version, shadow_model = router.select(request_id)
    text = extract_text(filename, data)
    sentences = [part.strip() for part in re.split(r"(?<=[.!?。！？])\s+|\n+", text) if part.strip()]
    if len(sentences) > MAX_SENTENCES:
        raise HTTPException(status_code=400, detail=f"Document exceeds {MAX_SENTENCES}-sentence limit")
    try:
        simplified, fallbacks = run_model(model, sentences)
    except Exception as exc:
        log_request(request_id, role, version, sentences, [], started, type(exc).__name__)
        raise HTTPException(status_code=500, detail="Model inference failed") from exc
    log_request(request_id, role, version, sentences, simplified, started, fallbacks=fallbacks)
    payload = {
        "model_version": version,
        "sentences": [
            {"original": original, "simple": simple, "fallback": fallback}  # fallback: 안전장치로 원문을 돌려준 문장(로그와 같은 값)
            for original, simple, fallback in zip(sentences, simplified, fallbacks)
        ],
    }
    return payload, sentences, shadow_version, shadow_model


def run_shadow(request_id: str, version: str, model, sentences: list[str]) -> None:
    started = time.perf_counter()
    if not SHADOW_SLOTS.acquire(blocking=False):
        log_request(request_id, "shadow", version, sentences, [], started, "shadow_busy")
        return
    try:
        try:
            output, fallbacks = run_model(model, sentences)
        except Exception as exc:
            log_request(request_id, "shadow", version, sentences, [], started, type(exc).__name__)
        else:
            log_request(request_id, "shadow", version, sentences, output, started, fallbacks=fallbacks)
    finally:
        SHADOW_SLOTS.release()


@app.post("/simplify")
async def simplify(background_tasks: BackgroundTasks, file: UploadFile = File(...)) -> dict:
    if not SIMPLIFY_SLOTS.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="Server is busy; retry shortly", headers={"Retry-After": "1"})
    try:
        if not file.filename or Path(file.filename).suffix.lower() not in {".txt", ".docx", ".hwpx", ".pdf"}:
            raise HTTPException(status_code=400, detail="Supported files: .txt, .docx, .hwpx, .pdf")
        data = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=400, detail="File exceeds 5 MB limit")
        if not data.strip():
            raise HTTPException(status_code=400, detail="File is empty")
        request_id = uuid.uuid4().hex
        payload, sentences, shadow_version, shadow_model = await run_in_threadpool(
            simplify_content, file.filename, data, request_id
        )
        if shadow_model is not None:
            background_tasks.add_task(run_shadow, request_id, shadow_version, shadow_model, sentences)
        return payload
    finally:
        SIMPLIFY_SLOTS.release()


@app.post("/feedback")
def feedback(item: Feedback) -> dict[str, bool]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = json.dumps(item.model_dump(), ensure_ascii=False) + "\n"
    with feedback_lock, (LOG_DIR / "feedback.jsonl").open("a", encoding="utf-8") as log:
        log.write(line)
    return {"saved": True}


FRONTEND_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"


@app.get("/{frontend_path:path}", include_in_schema=False)
def frontend(frontend_path: str) -> FileResponse:
    root = FRONTEND_DIST.resolve()
    requested = (root / frontend_path).resolve()
    if not requested.is_relative_to(root):
        raise HTTPException(status_code=404)
    if requested.is_file():
        return FileResponse(requested)
    if Path(frontend_path).suffix or not (root / "index.html").is_file():
        raise HTTPException(status_code=404)
    return FileResponse(root / "index.html")
