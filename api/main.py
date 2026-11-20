import io
import json
import logging
import os
import re
import shutil
import threading
import time
import uuid
import zipfile
import fcntl
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from starlette.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from api.router import ModelRouter
from simple_word.terms import terms_in

app = FastAPI()
LOG_DIR = Path(os.getenv("LOG_DIR", "./logs"))
router = ModelRouter(os.getenv("REGISTRY_PATH", "models/registry.json"))
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_UNPACKED_BYTES = 20 * 1024 * 1024
MAX_LOG_BYTES = 10 * 1024 * 1024
MAX_LOG_BACKUPS = 3
MIN_LOG_FREE_BYTES = 50 * 1024 * 1024
logger = logging.getLogger(__name__)
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
    return "\n\n".join(paragraphs)


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
    except HTTPException:
        raise
    except (UnicodeDecodeError, zipfile.BadZipFile, KeyError, ElementTree.ParseError, DefusedXmlException, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid {suffix[1:].upper()} file: {exc}") from exc
    raise HTTPException(status_code=400, detail="Supported files: .txt, .docx, .hwpx")


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
    append_jsonl("requests.jsonl", record, request_log_lock)


def append_jsonl(name: str, record: dict, lock: threading.Lock) -> bool:
    line = (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
    path = LOG_DIR / name
    if len(line) > MAX_LOG_BYTES:
        logger.warning("Skipping %s record larger than log limit", name)
        return False
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with lock, (LOG_DIR / f".{name}.lock").open("a") as guard:
            fcntl.flock(guard.fileno(), fcntl.LOCK_EX)
            if shutil.disk_usage(LOG_DIR).free < MIN_LOG_FREE_BYTES:
                logger.warning("Skipping %s write: less than %d bytes free", name, MIN_LOG_FREE_BYTES)
                return False
            if path.exists() and path.stat().st_size + len(line) > MAX_LOG_BYTES:
                for index in range(MAX_LOG_BACKUPS, 0, -1):
                    backup = path.with_name(f"{name}.{index}")
                    source = path if index == 1 else path.with_name(f"{name}.{index - 1}")
                    if index == MAX_LOG_BACKUPS:
                        backup.unlink(missing_ok=True)
                    if source.exists():
                        source.replace(backup)
            with path.open("ab") as log:
                log.write(line)
            return True
    except OSError as exc:
        logger.warning("Skipping %s write after filesystem error: %s", name, type(exc).__name__)
        return False


def run_model(model, sentences: list[str]) -> tuple[list[str], list[bool], list[str | None]]:
    """출력, fallback 여부, 이유를 돌려준다. 설명 함수가 없는 기존 모델은 이유를 비워 둔다."""
    explained = getattr(model, "simplify_explained", None)
    if explained is not None:
        triples = explained(sentences)
        return [text for text, _, _ in triples], [fallback for _, fallback, _ in triples], [reason for _, _, reason in triples]
    detailed = getattr(model, "simplify_detailed", None)
    if detailed is None:
        outputs = model.simplify(sentences)
        return outputs, [False] * len(outputs), [None] * len(outputs)
    pairs = detailed(sentences)
    return [text for text, _ in pairs], [fallback for _, fallback in pairs], [None] * len(pairs)


def simplify_content(filename: str, data: bytes, request_id: str):
    started = time.perf_counter()
    version, role, model, shadow_version, shadow_model = router.select(request_id)
    text = extract_text(filename, data)
    paragraphs = re.split(r"\n\s*\n+", text.strip())
    title = None
    if paragraphs:
        first_lines = paragraphs[0].splitlines()
        first_line = first_lines[0].strip() if first_lines else ""
        explicit_title = first_line.startswith("제목:") and bool(first_line.removeprefix("제목:").strip())
        short_heading = (
            len(paragraphs) > 1 and len(first_lines) == 1 and 2 <= len(first_line) <= 40
            and not re.search(r"[.!?。！？…][\"'”’）)]*$", first_line)
            and not re.search(r"(?:합니다|됩니다|있습니다|바랍니다|하세요|해주세요|입니다|한다|된다)$", first_line)
        )
        if explicit_title or short_heading:
            title = first_line
            paragraphs[0] = "\n".join(first_lines[1:]).strip()
            if not paragraphs[0]:
                paragraphs.pop(0)
    paragraph_sentences = [
        (paragraph_id + (title is not None), part.strip())
        for paragraph_id, paragraph in enumerate(paragraphs)
        for part in re.split(r"(?<=[.!?。！？])\s+|\n+", paragraph)
        if part.strip()
    ]
    sentences = [sentence for _, sentence in paragraph_sentences]
    if len(sentences) > MAX_SENTENCES:
        raise HTTPException(status_code=400, detail=f"Document exceeds {MAX_SENTENCES}-sentence limit")
    try:
        simplified, fallbacks, fallback_reasons = run_model(model, sentences)
    except Exception as exc:
        log_request(request_id, role, version, sentences, [], started, type(exc).__name__)
        raise HTTPException(status_code=500, detail="Model inference failed") from exc
    log_request(request_id, role, version, sentences, simplified, started, fallbacks=fallbacks)
    items = ([{"original": title, "simple": title, "fallback": False, "fallback_reason": None,
               "paragraph_id": 0, "title": True, "terms": []}] if title is not None else [])
    items.extend(
        {"original": original, "simple": simple, "fallback": fallback, "fallback_reason": reason,
         "paragraph_id": paragraph_id, "title": False, "terms": terms_in(original)}
        for (paragraph_id, original), simple, fallback, reason in zip(
            paragraph_sentences, simplified, fallbacks, fallback_reasons
        )
    )
    payload = {
        "model_version": version,
        "sentences": items,
    }
    return payload, sentences, shadow_version, shadow_model


def run_shadow(request_id: str, version: str, model, sentences: list[str]) -> None:
    started = time.perf_counter()
    if not SHADOW_SLOTS.acquire(blocking=False):
        log_request(request_id, "shadow", version, sentences, [], started, "shadow_busy")
        return
    try:
        try:
            output, fallbacks, _ = run_model(model, sentences)
        except Exception as exc:
            log_request(request_id, "shadow", version, sentences, [], started, type(exc).__name__)
        else:
            log_request(request_id, "shadow", version, sentences, output, started, fallbacks=fallbacks)
    finally:
        SHADOW_SLOTS.release()


@app.post("/simplify")
async def simplify(background_tasks: BackgroundTasks, file: UploadFile = File(...)) -> dict:
    filename = file.filename or ""
    suffix = Path(filename).suffix.lower()
    media_type = (file.content_type or "").split(";", 1)[0].strip().lower()
    if suffix == ".pdf" or media_type == "application/pdf":
        raise HTTPException(status_code=415, detail="PDF 파일은 지원하지 않아요. TXT, DOCX, HWPX 파일을 올려 주세요.")
    if not SIMPLIFY_SLOTS.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="Server is busy; retry shortly", headers={"Retry-After": "1"})
    try:
        if not filename or suffix not in {".txt", ".docx", ".hwpx"}:
            raise HTTPException(status_code=400, detail="Supported files: .txt, .docx, .hwpx")
        data = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=400, detail="File exceeds 5 MB limit")
        if not data.strip():
            raise HTTPException(status_code=400, detail="File is empty")
        request_id = uuid.uuid4().hex
        payload, sentences, shadow_version, shadow_model = await run_in_threadpool(
            simplify_content, filename, data, request_id
        )
        if shadow_model is not None:
            background_tasks.add_task(run_shadow, request_id, shadow_version, shadow_model, sentences)
        return payload
    finally:
        SIMPLIFY_SLOTS.release()


@app.post("/feedback")
def feedback(item: Feedback) -> dict[str, bool]:
    record = item.model_dump()
    record["original"] = redact(record["original"])
    record["simple"] = redact(record["simple"])
    if not append_jsonl("feedback.jsonl", record, feedback_lock):
        raise HTTPException(status_code=503, detail="Feedback logging temporarily unavailable",
                            headers={"Retry-After": "30"})
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
