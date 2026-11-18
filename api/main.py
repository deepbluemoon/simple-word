import re

from fastapi import FastAPI, File, HTTPException, UploadFile

from simple_word.model import Simplifier

app = FastAPI()
simplifier = Simplifier(artifact_dir="models")
MODEL_VERSION = "dummy"


@app.get("/health")
def health() -> dict[str, list[str]]:
    return {"model_versions": [MODEL_VERSION]}


@app.post("/simplify")
async def simplify(file: UploadFile = File(...)) -> dict:
    if not file.filename or not file.filename.lower().endswith(".txt"):
        raise HTTPException(status_code=400, detail="Only .txt files are supported")

    try:
        text = (await file.read()).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="File must be UTF-8 text") from exc

    sentences = [part.strip() for part in re.split(r"(?<=[.!?。！？])\s+|\n+", text) if part.strip()]
    simplified = simplifier.simplify(sentences)
    return {
        "model_version": MODEL_VERSION,
        "sentences": [
            {"original": original, "simple": simple}
            for original, simple in zip(sentences, simplified)
        ],
    }
