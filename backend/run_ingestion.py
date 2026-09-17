"""
run_ingestion.py
Full-document validation run: rasterizes the given PDF fresh, then runs
every page through parse_document(), end to end. Not part of the live
pipeline itself - a one-off script for running the extractor directly
against a sample PDF, without going through the upload API.

Replaces run_full_ingestion.py / run_full_ingestion_clean.py, which were
two separate hardcoded-PDF_PATH scripts that became identical in structure
once both were fixed to rasterize fresh instead of assuming pre-rendered
pages/TESTDOC_*.png / pages/CLEANDOC_*.png existed - real duplication, not
two genuinely different scripts, so they were merged into this one
argument-driven version instead of kept in sync by hand.

Uses the same doc_slug convention as the real upload path (routers/
upload.py: Path(file.filename).stem) so this script's behavior matches
what actually uploading the given PDF through the API would do.

Usage:
    venv/Scripts/python.exe run_ingestion.py "C:\\path\\to\\document.pdf" [doc_type]

    doc_type defaults to "WCR" if omitted (pass "DDR" for a Daily Drilling
    Report instead).
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")
from src.pdf_processor import rasterize_pdf
from src.unified_parser import parse_document
from src.database import get_document, get_well, get_hazards_for_well

if len(sys.argv) < 2:
    print('Usage: venv/Scripts/python.exe run_ingestion.py "C:\\path\\to\\document.pdf" [doc_type]')
    sys.exit(1)

PDF_PATH = sys.argv[1]
DOC_TYPE = sys.argv[2] if len(sys.argv) > 2 else "WCR"

if not Path(PDF_PATH).exists():
    print(f"File not found: {PDF_PATH}")
    sys.exit(1)

doc_slug = Path(PDF_PATH).stem
print(f"Rasterizing {PDF_PATH} (slug: {doc_slug})...")
pages = rasterize_pdf(PDF_PATH, doc_slug)
print(f"Rasterized {len(pages)} page(s).")

print(f"Starting full ingestion of {len(pages)} pages at {time.strftime('%H:%M:%S')}")
start = time.time()
result = parse_document(pdf_path=PDF_PATH, pages=pages, doc_type=DOC_TYPE)
elapsed = time.time() - start

print(f"\nDone in {elapsed / 60:.1f} min ({elapsed:.0f}s)")
print("=" * 70)
print("parse_document() result:", result)
print("=" * 70)

if result["status"] != "REJECTED_DUPLICATE":
    print("\ndocument row:")
    print(get_document(result["document_id"]))
    print("\nwell row:")
    print(get_well(result["well_id"]))
    print("\nall hazards for this well:")
    for h in get_hazards_for_well(result["well_id"]):
        print(" ", h)
