"""Parse an authorized local PDF, preserve page references, and submit it to the private ingestion API."""
import argparse
import base64
import json
import os
import re
from pathlib import Path

import httpx
from dotenv import load_dotenv

from .knowledge import Source


def split_page(text, length=1100):
    compact = re.sub(r"\s+", " ", text).strip()
    start = 0
    while len(compact) - start >= 20:
        end = min(start + length, len(compact))
        if end < len(compact):
            split = max(compact.rfind(mark, start + length // 2, end) for mark in ("。", ". ", "；", " "))
            if split >= 0:
                end = split + 1
        yield compact[start:end].strip()
        start = end


def main():
    import pymupdf

    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("metadata", type=Path, help="Source JSON without id, text and page_number")
    parser.add_argument("--api", default="http://127.0.0.1:8080")
    parser.add_argument("--ocr", help="Tesseract languages, for example chi_sim+eng")
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    token = os.getenv("HEALTH_AI_INGEST_TOKEN")
    if not token:
        parser.error("Set HEALTH_AI_INGEST_TOKEN")
    if not (args.api.startswith("https://") or args.api in {"http://localhost:8080", "http://127.0.0.1:8080"}):
        parser.error("Use HTTPS or the default local service")
    raw = args.pdf.read_bytes()
    if len(raw) > 1_000_000:
        parser.error("Import one authorized document of at most 1 MB at a time")
    metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
    records = []
    with pymupdf.open(stream=raw, filetype="pdf") as document:
        for page in document:
            text = page.get_text()
            if len(text.strip()) < 20 and args.ocr:
                page_text = page.get_textpage_ocr(language=args.ocr, dpi=150)
                text = page.get_text(textpage=page_text)
            for number, chunk in enumerate(split_page(text), 1):
                record = Source.model_validate({
                    **metadata, "id": f"{metadata['document_id']}-p{page.number + 1}-{number}",
                    "page_number": page.number + 1, "text": chunk, "excerpt_kind": "original",
                    "status": metadata.get("status", "unverified"),
                })
                records.append(record.model_dump(mode="json"))
    if not records or len(records) > 24:
        parser.error("This import needs 1–24 extractable chunks. Split longer licensed documents into sections.")
    response = httpx.post(args.api.rstrip("/") + "/api/ingest", timeout=120, headers={
        "Authorization": "Bearer " + token,
    }, json={
        "sources": records, "media_type": "application/pdf", "artifact_base64": base64.b64encode(raw).decode()
    })
    response.raise_for_status()
    print(json.dumps(response.json(), ensure_ascii=False))


if __name__ == "__main__":
    main()
