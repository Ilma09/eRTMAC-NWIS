"""
corpus.py
GET /api/corpus, GET /api/corpus/{id}, GET /api/corpus/{id}/file

Response shape matches Corpus.jsx's REAL mock data exactly (read directly from
the actual .jsx source, not the frontend description doc - which described a
different, simpler shape than what the component actually uses):
    {id, name, type, well, region, date, pages, status, size}

"id" is a synthesized string ("WCR-0001"), not the raw integer document_id,
to match the mock's "WCR-1042" style ids - _parse_corpus_id() below reverses
this to look a document back up.
"""
import os
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from src import database

router = APIRouter(prefix="/api/corpus", tags=["corpus"])

# Frontend's real status vocabulary ("Processed"/"Review" - a select dropdown
# with only those two plus "All") differs from the backend's internal status
# enum (COMPLETE/NEEDS_REVIEW/PROCESSING/FAILED) - mapped here, once, rather
# than baking frontend vocabulary into the database.
_STATUS_MAP = {
    "COMPLETE": "Processed",
    "NEEDS_REVIEW": "Review",
    "PROCESSING": "Processing",
    "FAILED": "Failed",
}

_DOC_TITLE = {"WCR": "Well Completion Report", "DDR": "Daily Drilling Report"}


def _format_size(file_path: str) -> str:
    try:
        size_bytes = os.path.getsize(file_path)
    except OSError:
        return "Unknown"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def _format_date(uploaded_at) -> str:
    if not uploaded_at:
        return ""
    try:
        return datetime.strptime(uploaded_at[:19], "%Y-%m-%d %H:%M:%S").strftime("%d %b %Y")
    except ValueError:
        return uploaded_at


def _build_corpus_item(document: dict) -> dict:
    well = database.get_well(document["well_id"]) if document.get("well_id") else None
    doc_type = document.get("doc_type") or "WCR"
    well_name = well["well_name"] if well else None
    return {
        "id": f"{doc_type}-{document['document_id']:04d}",
        "name": f"{_DOC_TITLE.get(doc_type, doc_type)} - {well_name or document['filename']}",
        "type": doc_type,
        "well": well_name or "Unknown",
        "region": (well.get("field_location") if well else None) or "Unknown",
        "date": _format_date(document.get("uploaded_at")),
        "pages": document.get("page_count") or 0,
        "status": _STATUS_MAP.get(document.get("status"), document.get("status")),
        "size": _format_size(document["file_path"]),
    }


def _resolve_document_id(corpus_id: str) -> int:
    """"WCR-0001" -> 1. Raises 404 rather than 400/500 for a malformed id -
    from the client's perspective a bad id and a missing document look the same."""
    try:
        return int(corpus_id.rsplit("-", 1)[-1])
    except (ValueError, IndexError):
        raise HTTPException(status_code=404, detail="Document not found")


@router.get("")
def list_corpus():
    return [_build_corpus_item(doc) for doc in database.list_documents()]


@router.get("/{corpus_id}")
def get_corpus_item(corpus_id: str):
    document = database.get_document(_resolve_document_id(corpus_id))
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return _build_corpus_item(document)


@router.get("/{corpus_id}/file")
def get_corpus_file(corpus_id: str):
    document = database.get_document(_resolve_document_id(corpus_id))
    if document is None or not os.path.exists(document["file_path"]):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        document["file_path"], filename=document["filename"], media_type="application/pdf"
    )


@router.delete("/{corpus_id}")
def delete_corpus_item(corpus_id: str):
    document_id = _resolve_document_id(corpus_id)
    document = database.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    well_id = database.delete_document(document_id)

    # Only remove the well if no other document still references it - a well
    # can legitimately have more than one document linked to it (dedup by
    # well name), so deleting it here unconditionally would risk destroying
    # a still-valid well backed by a different document.
    if well_id is not None and database.count_documents_for_well(well_id) == 0:
        database.delete_well(well_id)

    try:
        if os.path.exists(document["file_path"]):
            os.remove(document["file_path"])
    except OSError:
        pass  # best-effort - the DB rows are already gone, a leftover file on disk isn't worth failing the request over

    return {"status": "deleted"}
