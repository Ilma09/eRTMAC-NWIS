"""
review_document_pages.py
Standalone review tool: prints (and saves to a text file) a page-by-page
breakdown of what was actually extracted from an already-processed document -
rendered image path, Pass 1 header fields (pages 1-2 only), Pass 2 transcribed
text, and any hazards found on that page with their confidence tier.

This document predates the page_extractions/image_artifacts persistence added
alongside this script - that data was never saved for it, so this script
re-extracts live (real VLM time per page) and persists results as it goes via
database.upsert_page_extraction()/create_image_artifact(), same as
run_extraction() now does going forward. A document processed after this
change would already have page_text saved and wouldn't need re-extraction to
review - this script still re-extracts unconditionally for simplicity, not
because it always has to.

Usage: venv/Scripts/python.exe review_document_pages.py <document_id> [start_page] [end_page]
"""
import json
import sys

sys.path.insert(0, ".")
from src import database
from src.unified_parser import extract_header_fields, extract_page_content

# Fallback for documents that predate image_artifacts being populated -
# these two are the only documents in the database right now.
_LEGACY_IMAGE_PREFIX = {10: "TESTDOC", 11: "CLEANDOC"}


def _image_path_for(document_id: int, page_num: int) -> str:
    artifacts = database.get_image_artifacts_for_document(document_id)
    for artifact in artifacts:
        if artifact["page_num"] == page_num:
            return artifact["file_path"]
    prefix = _LEGACY_IMAGE_PREFIX.get(document_id)
    if prefix is None:
        raise ValueError(f"No image_artifacts row and no known legacy prefix for document_id={document_id}")
    return f"pages/{prefix}_p{page_num}_full.png"


def review(document_id: int, start_page: int, end_page: int) -> str:
    document = database.get_document(document_id)
    if document is None:
        raise ValueError(f"No document with document_id={document_id}")
    well = database.get_well(document["well_id"]) if document.get("well_id") else None

    lines = []
    lines.append(f"Document {document_id}: {document['filename']} ({document['status']})")
    if well:
        lines.append(f"Well: {well['well_name']} (well_id={well['well_id']})")
    lines.append("=" * 78)

    for page_num in range(start_page, end_page + 1):
        image_path = _image_path_for(document_id, page_num)
        lines.append(f"\n--- PAGE {page_num} ---")
        lines.append(f"Image: {image_path}")

        # Pass 1 only covers pages 1-2, per the architecture spec.
        if page_num <= 2:
            header_fields, pass1_ok = extract_header_fields(image_path)
            database.upsert_page_extraction(
                document_id=document_id,
                page_num=page_num,
                parse_ok=pass1_ok,
                header_fields_json=json.dumps(header_fields),
            )
            lines.append(f"\nPass 1 header fields (parse_ok={pass1_ok}):")
            for field_name, (value, confidence) in header_fields.items():
                lines.append(f"  {field_name}: {value!r} [{confidence}]")

        content = extract_page_content(image_path)
        database.upsert_page_extraction(
            document_id=document_id,
            page_num=page_num,
            page_text=content["page_text"],
            parse_ok=content["parse_ok"],
        )
        lines.append(
            f"\nPass 2 transcribed text (parse_ok={content['parse_ok']}, "
            f"text_possibly_truncated={content.get('text_possibly_truncated')}):"
        )
        lines.append(content["page_text"] or "(empty)")

        hazards_on_page = [
            h for h in (database.get_hazards_for_well(well["well_id"]) if well else []) if h["page_num"] == page_num
        ]
        lines.append(f"\nHazards found on this page: {len(hazards_on_page)}")
        for hazard in hazards_on_page:
            lines.append(
                f"  - {hazard['hazard_type']} @ {hazard['depth_m']}m "
                f"[{hazard['confidence']} confidence, {hazard['severity']} severity]"
            )
            lines.append(f"    {hazard['description']}")

        lines.append("-" * 78)

    return "\n".join(lines)


if __name__ == "__main__":
    doc_id = int(sys.argv[1])
    start = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    end = int(sys.argv[3]) if len(sys.argv) > 3 else 5

    report = review(doc_id, start, end)
    out_path = f"page_review_doc{doc_id}_p{start}-{end}.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(report)
    print(f"\n\n(also saved to {out_path})")
