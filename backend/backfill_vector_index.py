"""
backfill_vector_index.py
One-off script: indexes every already-processed document's page text into
Qdrant, for documents that were ingested before vector_store.index_page()
was actually wired into run_extraction()/resume_extraction() (a real gap
found directly, not hypothetical - see unified_parser.py's docstring, which
documented indexing as "not built yet" while nothing ever called it; Qdrant
held only 2 leftover test chunks before this).

Safe to run any time, including after the fix above is in place: index_page()
upserts by a deterministic (document_id, page_num) ID, so re-indexing an
already-indexed page is a harmless no-op, not a duplicate.

Usage:
    venv/Scripts/python.exe backfill_vector_index.py
"""
import sys

sys.path.insert(0, ".")
from src import database, vector_store

documents = database.list_documents()
print(f"Found {len(documents)} document(s) to check.")

total_indexed = 0
total_skipped_empty = 0
for document in documents:
    document_id = document["document_id"]
    well_id = document.get("well_id")
    extractions = database.get_page_extractions_for_document(document_id)
    indexed_here = 0
    for extraction in extractions:
        if vector_store.index_page(
            well_id=well_id,
            document_id=document_id,
            page_num=extraction["page_num"],
            page_text=extraction.get("page_text"),
        ):
            indexed_here += 1
        else:
            total_skipped_empty += 1
    total_indexed += indexed_here
    print(f"  document_id={document_id} ({document['filename']}): indexed {indexed_here}/{len(extractions)} page(s)")

print()
print(f"Total pages indexed this run: {total_indexed}")
print(f"Total pages skipped (empty/failed text, nothing to index): {total_skipped_empty}")
print(f"Qdrant now holds {vector_store.count_indexed_chunks()} chunk(s) total.")
