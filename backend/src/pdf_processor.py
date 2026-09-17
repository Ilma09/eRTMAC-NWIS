"""
pdf_processor.py
Step 1 of the pipeline: rasterizes an uploaded PDF into 200 DPI PNG page images
using pypdfium2 (Google's pdfium C++ engine, no system deps like Poppler needed).
Saves renders into pages/ and returns their paths for the next pipeline stage.
"""

from pathlib import Path
from typing import List

import pypdfium2 as pdfium

from src.config import MAX_RENDER_DIMENSION_PX, PAGES_DIR, RENDER_DPI


def _dpi_to_scale(dpi: int) -> float:
    """pypdfium2 render_to takes a 'scale' multiplier where 1.0 == 72 DPI (PDF's native unit)."""
    return dpi / 72.0


def _scale_for_page(page_width_pt: float, page_height_pt: float, dpi: int) -> float:
    """
    Normally just the flat DPI-based scale - but caps the LONGER rendered
    side at MAX_RENDER_DIMENSION_PX regardless of DPI, for the physically
    oversized pages this was found necessary for (see config.py's comment -
    verified directly against a real 19.3in x 25in source page that a flat
    200 DPI render produces an ~19 megapixel image Ollama's vision call
    fails on, reliably, and that capping the render size fixes it). A normal
    letter/A4 page is well under the cap at 200 DPI and is unaffected.
    """
    dpi_scale = _dpi_to_scale(dpi)
    longer_side_pt = max(page_width_pt, page_height_pt)
    if longer_side_pt <= 0:
        return dpi_scale
    cap_scale = MAX_RENDER_DIMENSION_PX / longer_side_pt
    return min(dpi_scale, cap_scale)


def rasterize_pdf(pdf_path: str, doc_slug: str) -> List[dict]:
    """
    Renders every page of the given PDF to a PNG at 200 DPI - or smaller,
    if that would exceed MAX_RENDER_DIMENSION_PX (see _scale_for_page).

    Args:
        pdf_path: absolute path to the source PDF file.
        doc_slug: short identifier used in output filenames (e.g. well name or doc id),
                  sanitized to be filesystem-safe by the caller.

    Returns:
        A list of dicts: [{"page_num": 1, "image_path": "...pages/W-103_p1_full.png"}, ...]
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    results = []

    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        page_count = len(pdf)
        # Prints so this step is visible in the terminal - rasterization used
        # to run completely silently, which made it look like nothing was
        # happening between "file uploaded" and "Pass 1 started" for however
        # long a large PDF took to render.
        print(f"[pdf_processor] Rasterizing {page_count} page(s) from {pdf_path.name}...", flush=True)
        for page_index in range(page_count):
            page = pdf[page_index]
            page_width_pt, page_height_pt = page.get_size()
            scale = _scale_for_page(page_width_pt, page_height_pt, RENDER_DPI)
            bitmap = page.render(scale=scale)
            pil_image = bitmap.to_pil()
 
            page_num = page_index + 1  # human-readable, 1-indexed
            out_filename = f"{doc_slug}_p{page_num}_full.png"
            out_path = PAGES_DIR / out_filename
 
            pil_image.save(out_path, format="PNG")
 
            results.append(
                {
                    "page_num": page_num,
                    "image_path": str(out_path),
                    "width": pil_image.width,
                    "height": pil_image.height,
                }
            )
 
            # Free page resources explicitly; large multi-page PDFs can otherwise
            # hold onto memory longer than needed during a long rasterization loop.
            page.close()
    finally:
        pdf.close()

    print(f"[pdf_processor] Rasterization done: {len(results)} page image(s) saved to {PAGES_DIR}", flush=True)
    return results
 
 
def get_page_count(pdf_path: str) -> int:
    """Quick page count without rendering — used at upload time before the full pipeline runs."""
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        return len(pdf)
    finally:
        pdf.close()
 
