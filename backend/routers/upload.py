"""
upload.py
POST /api/upload

Per the finalized design decision: returns a document_id immediately
(status: PROCESSING) and runs the slow VLM extraction as a background task -
NOT a blocking synchronous request. The frontend polls GET /api/corpus/{id}
to watch status transition PROCESSING -> COMPLETE / NEEDS_REVIEW / FAILED.

Rasterization (fast, CPU-only, seconds not minutes) happens synchronously in
the request so register_document() has a real page count/pages list to work
with; only the VLM extraction (run_extraction, minutes) is backgrounded.

Upload.jsx currently has no working upload call at all (handleUpload() just
fakes a setTimeout) and supports a third "TABLE" (CSV/Excel well data) type
alongside WCR/DDR - TABLE is out of scope here, it isn't part of the
documented WCR/DDR OCR pipeline.
"""
import shutil
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from src import pdf_processor, unified_parser
from src.config import UPLOADS_DIR

router = APIRouter(prefix="/api/upload", tags=["upload"])

_ALLOWED_DOC_TYPES = {"WCR", "DDR"}


@router.post("")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    doc_type: str = Form("WCR"),
):
    doc_type = doc_type.upper()
    if doc_type not in _ALLOWED_DOC_TYPES:
        raise HTTPException(status_code=400, detail=f"doc_type must be one of {sorted(_ALLOWED_DOC_TYPES)}")
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are currently supported")

    # First visible line of the whole pipeline in the terminal - everything
    # after this (rasterizing, Pass 1, Pass 2) prints its own progress too,
    # so the full upload -> OCR chain is watchable end to end.
    print(f"[upload] Received '{file.filename}' as {doc_type}", flush=True)

    dest_path = UPLOADS_DIR / file.filename
    with open(dest_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    pages = pdf_processor.rasterize_pdf(str(dest_path), Path(file.filename).stem)
    registration = unified_parser.register_document(str(dest_path), pages, doc_type=doc_type)

    if registration["status"] == "REJECTED_DUPLICATE":
        print(f"[upload] Rejected - duplicate of an already-ingested document", flush=True)
        return {
            "document_id": registration["document_id"],
            "status": "REJECTED_DUPLICATE",
            "message": registration.get("message"),
        }

    document_id = registration["document_id"]
    print(f"[upload] Registered as document_id={document_id} - handing off to background OCR extraction", flush=True)
    background_tasks.add_task(unified_parser.run_extraction, document_id, pages)

    return {"document_id": document_id, "status": "PROCESSING"}
