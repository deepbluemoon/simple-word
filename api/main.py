import io
import json
import os
import re
import threading
import zipfile
from pathlib import Path
from typing import Literal
from xml.etree import ElementTree

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from simple_word.model import Simplifier

app = FastAPI()
simplifier = Simplifier(artifact_dir="models")
MODEL_VERSION = "dummy"
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_UNPACKED_BYTES = 20 * 1024 * 1024
MAX_PDF_PAGES = 50
MAX_SENTENCES = 500
LOG_DIR = Path(os.getenv("LOG_DIR", "./logs"))
feedback_lock = threading.Lock()


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
def health() -> dict[str, list[str]]:
    return {"model_versions": [MODEL_VERSION]}


def simplify_content(filename: str, data: bytes) -> dict:
    text = extract_text(filename, data)
    sentences = [part.strip() for part in re.split(r"(?<=[.!?。！？])\s+|\n+", text) if part.strip()]
    if len(sentences) > MAX_SENTENCES:
        raise HTTPException(status_code=400, detail="Document exceeds 500-sentence limit")
    simplified = simplifier.simplify(sentences)
    return {
        "model_version": MODEL_VERSION,
        "sentences": [
            {"original": original, "simple": simple}
            for original, simple in zip(sentences, simplified)
        ],
    }


@app.post("/simplify")
async def simplify(file: UploadFile = File(...)) -> dict:
    if not file.filename or Path(file.filename).suffix.lower() not in {".txt", ".docx", ".hwpx", ".pdf"}:
        raise HTTPException(status_code=400, detail="Supported files: .txt, .docx, .hwpx, .pdf")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="File exceeds 5 MB limit")
    if not data.strip():
        raise HTTPException(status_code=400, detail="File is empty")
    return await run_in_threadpool(simplify_content, file.filename, data)


@app.post("/feedback")
def feedback(item: Feedback) -> dict[str, bool]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = json.dumps(item.model_dump(), ensure_ascii=False) + "\n"
    with feedback_lock, (LOG_DIR / "feedback.jsonl").open("a", encoding="utf-8") as log:
        log.write(line)
    return {"saved": True}


app.mount("/", StaticFiles(directory="web", html=True), name="web")
