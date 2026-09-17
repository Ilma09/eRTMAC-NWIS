"""
resume_ingestion.py
Re-runs extraction ONLY for pages that previously failed to parse, for an
already-registered document - see unified_parser.resume_extraction()'s
docstring for why this exists (Ollama's background auto-updater killed the
server mid-run on a real 33-page document, pages 9-33 all failed with no
recovery after pages 1-8 succeeded normally).

Reuses the page images already rendered and recorded in image_artifacts
during the original run - does not re-rasterize the PDF.

Usage:
    venv/Scripts/python.exe resume_ingestion.py <document_id>
"""
import sys

sys.path.insert(0, ".")
from src.database import get_document, get_hazards_for_well, get_image_artifacts_for_document, get_well
from src.unified_parser import resume_extraction

if len(sys.argv) < 2:
    print("Usage: venv/Scripts/python.exe resume_ingestion.py <document_id>")
    sys.exit(1)

document_id = int(sys.argv[1])
document = get_document(document_id)
if document is None:
    print(f"No document with document_id={document_id}")
    sys.exit(1)

artifacts = [a for a in get_image_artifacts_for_document(document_id) if a["artifact_kind"] == "PAGE_RENDER"]
if not artifacts:
    print(f"No PAGE_RENDER image_artifacts found for document_id={document_id} - cannot resume without page images")
    sys.exit(1)

pages = sorted(
    ({"page_num": a["page_num"], "image_path": a["file_path"]} for a in artifacts),
    key=lambda p: p["page_num"],
)
print(f"Found {len(pages)} page image(s) already on disk for document_id={document_id} ({document['filename']})")

result = resume_extraction(document_id, pages)

print()
print("=" * 70)
print("resume_extraction() result:", result)
print("=" * 70)

if document.get("well_id"):
    print("\nwell row:")
    print(get_well(document["well_id"]))
    print("\nall hazards for this well:")
    for h in get_hazards_for_well(document["well_id"]):
        print(" ", h)
