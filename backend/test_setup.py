import sys
sys.path.insert(0, '.')
from src.pdf_processor import rasterize_pdf, get_page_count
from src.database import init_db, create_document, create_well, count_wells, count_documents

init_db()
print("DB init: OK")

pdf_path = "C:\\Users\\papna\\Downloads\\gujarat_well_completion_report_final_notes_moved_down.pdf" # point this at a real PDF you have
pc = get_page_count(pdf_path)
print(f"Page count: {pc}")

results = rasterize_pdf(pdf_path, "TESTDOC")
print(f"Rasterized {len(results)} pages")
print("First page:", results[0])

doc_id = create_document("test.pdf", "WCR", pdf_path, pc)
well_id = create_well("Test Well X-1", "OIL India", 27.5, 95.3, 3200.0, document_id=doc_id)
print("Inserted doc_id:", doc_id, "well_id:", well_id)
print("count_documents:", count_documents())
print("count_wells:", count_wells())