"""
One-off backfill: populates well-comparison enrichment fields (formation,
mud_type, mud_weight, casing_notes, cementing_notes, reservoir_notes) on
every well ingested before these fields existed, using ONLY their
already-transcribed page text (derive_well_enrichment - regex-based, no VLM
call, cannot affect the image-based extraction pipeline in any way). Safe to
re-run.

Must be run with the backend server stopped OR while it's running - this
script only reads/writes SQLite, it never touches Qdrant, so it does not hit
the single-writer lock issue that standalone Qdrant-touching scripts do.
"""
from src import database, unified_parser

database.init_db()  # applies the enrichment-columns migration if not already applied

wells = database.list_wells()
print(f"Checking {len(wells)} well(s)...")

updated = 0
for well in wells:
    document_id = well.get("document_id")
    if document_id is None:
        print(f"  well {well['well_id']} ({well['well_name']}): no linked document, skipping")
        continue

    extractions = database.get_page_extractions_for_document(document_id)
    page_texts = [e.get("page_text") for e in extractions]

    enrichment = unified_parser.derive_well_enrichment(page_texts)

    if all(v is None for v in enrichment.values()):
        print(f"  well {well['well_id']} ({well['well_name']}): nothing found")
        continue

    database.update_well_enrichment(well["well_id"], **enrichment)
    updated += 1
    print(f"  well {well['well_id']} ({well['well_name']}): {enrichment}")

print(f"Done. Updated {updated}/{len(wells)} well(s).")
