"""
review.py
Standalone OCR review tool - explicitly NOT part of the ertmac-nwis React app
(that's being built separately). Plain server-rendered HTML + vanilla JS, no
build step, served directly by this same FastAPI backend at a different path
prefix (/review) so it can't collide with the real frontend's routes.

Left pane: the rendered page image. Right pane: a single editable
contenteditable box, seeded with real rendered HTML (table_parser.py's
render_page_as_html) - any detected pipe-delimited table run becomes a
genuine <table> with real rows/columns, not markdown text, since a plain
<textarea> can only ever display flat characters and can never visually
render as a bordered grid. Editing happens directly in this same view (type
in a table cell, or in the surrounding text) - there is no separate
read-only preview. Saving serializes the current DOM back to plain text
(tables become markdown pipe rows again) into page_extractions.corrected_text
- a column separate from page_text, so the original model output is never
overwritten. Download exports whichever text is "current" (corrected if
present, else the original with tables reformatted) as a .txt file.
"""
import json
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from review_document_pages import _image_path_for  # reuse the same image-path resolution, don't duplicate it

from src import database
from src.table_parser import render_page_as_html, render_page_with_tables
from src.unified_parser import looks_incomplete

router = APIRouter(tags=["review"])


class CorrectionPayload(BaseModel):
    text: str


@router.get("/api/review/{document_id}/pages")
def list_pages(document_id: int):
    document = database.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    extractions = {e["page_num"]: e for e in database.get_page_extractions_for_document(document_id)}
    return {
        "document_id": document_id,
        "filename": document["filename"],
        "page_count": document.get("page_count") or 0,
        "pages": [
            {
                "page_num": p,
                "has_extraction": p in extractions,
                "has_correction": bool(extractions.get(p, {}).get("corrected_text")),
                # None when no row exists yet (genuinely not reached), 0/1 once
                # Pass 2 has actually run - lets the page strip show a hard
                # failure distinctly from "not yet attempted" (see get_page's
                # own parse_ok field for the full explanation).
                "parse_ok": extractions.get(p, {}).get("parse_ok") if p in extractions else None,
            }
            for p in range(1, (document.get("page_count") or 0) + 1)
        ],
    }


@router.get("/api/review/{document_id}/{page_num}")
def get_page(document_id: int, page_num: int):
    document = database.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    extraction = database.get_page_extraction(document_id, page_num)
    well = database.get_well(document["well_id"]) if document.get("well_id") else None
    hazards = [h for h in (database.get_hazards_for_well(well["well_id"]) if well else []) if h["page_num"] == page_num]
    header_fields = json.loads(extraction["header_fields"]) if extraction and extraction.get("header_fields") else None

    # Both run read-only, at request time - no VLM call, no DB write, safe on
    # every view. Whichever text is "current" (the human's correction if one
    # was saved, else the raw model output) drives both: seed_text (plain,
    # tables as markdown pipe rows) is what a fresh save round-trips to if the
    # human doesn't touch the table at all and is what feeds the truncation
    # heuristic; rendered_html (real <table> markup) is what the browser
    # actually displays and lets the human edit directly.
    corrected_text = extraction.get("corrected_text") if extraction else None
    raw_text = extraction.get("page_text") if extraction else None
    current_text = corrected_text if corrected_text else raw_text
    table_view = render_page_with_tables(current_text)
    seed_text = table_view["text_with_tables_formatted"]
    html_view = render_page_as_html(current_text)

    return {
        "page_num": page_num,
        "original_text": extraction["page_text"] if extraction else None,
        "corrected_text": extraction.get("corrected_text") if extraction else None,
        "header_fields": header_fields,
        "hazards": hazards,
        # True only when a page_extractions row exists at all - NOT the same
        # as "extraction succeeded". A page that was attempted and hard-failed
        # (parse_ok=0) still gets a row (see unified_parser.extract_page_content
        # and upsert_page_extraction), so callers must check parse_ok below to
        # tell "genuinely not reached yet" apart from "attempted and failed".
        "has_extraction": extraction is not None,
        "parse_ok": extraction.get("parse_ok") if extraction else None,
        "failure_reason": extraction.get("failure_reason") if extraction else None,
        # Real HTML for the editable OCR view - genuine <table> markup for
        # detected regions, not markdown text (a <textarea> can never render
        # as a bordered grid regardless of what characters are inside it).
        "rendered_html": html_view["html"],
        "text_possibly_truncated": looks_incomplete(seed_text),
        "detected_tables": table_view["tables"],
    }


@router.get("/api/review/{document_id}/{page_num}/image")
def get_page_image(document_id: int, page_num: int):
    try:
        image_path = _image_path_for(document_id, page_num)
    except ValueError:
        raise HTTPException(status_code=404, detail="No image found for this page")
    return FileResponse(image_path)


@router.post("/api/review/{document_id}/{page_num}/correction")
def save_correction(document_id: int, page_num: int, payload: CorrectionPayload):
    if database.get_page_extraction(document_id, page_num) is None:
        raise HTTPException(status_code=404, detail="No extraction exists yet for this page - nothing to correct")
    database.save_corrected_text(document_id, page_num, payload.text)
    return {"status": "saved"}


@router.get("/api/review/{document_id}/{page_num}/download")
def download_page_text(document_id: int, page_num: int):
    extraction = database.get_page_extraction(document_id, page_num)
    if extraction is None:
        raise HTTPException(status_code=404, detail="No extraction exists yet for this page")
    # Same "whichever is current" rule as get_page(): a saved correction's own
    # pipe-delimited rows (if any) get reformatted too, consistent with what
    # the editable view shows - not a special case for downloads.
    current_text = extraction.get("corrected_text") or extraction.get("page_text")
    text = render_page_with_tables(current_text)["text_with_tables_formatted"]
    return PlainTextResponse(
        text,
        headers={"Content-Disposition": f'attachment; filename="doc{document_id}_page{page_num}.txt"'},
    )


@router.get("/review/{document_id}", response_class=HTMLResponse)
def review_page(document_id: int):
    return _REVIEW_HTML.replace("__DOCUMENT_ID__", str(document_id))


_REVIEW_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>OCR Review - Document __DOCUMENT_ID__</title>
<style>
  body { margin: 0; font-family: system-ui, sans-serif; background: #1a1a1a; color: #ddd; }
  header { padding: 10px 16px; background: #262626; border-bottom: 1px solid #3a3a3a; display: flex; align-items: center; gap: 12px; }
  header h1 { font-size: 15px; margin: 0; flex: 1; }
  header button, header input { background: #333; color: #ddd; border: 1px solid #555; border-radius: 4px; padding: 6px 10px; cursor: pointer; }
  header input { width: 60px; cursor: text; text-align: center; }
  .main { display: flex; height: calc(100vh - 48px); }
  .pane { flex: 1; overflow: auto; padding: 12px; box-sizing: border-box; }
  .pane img { max-width: 100%; display: block; margin: 0 auto; border: 1px solid #444; }
  #textBox { width: 100%; height: 60%; box-sizing: border-box; overflow-y: auto; background: #f5f2e8; color: #1a1a1a; border: 1px solid #444; border-radius: 4px; padding: 10px 14px; font-family: system-ui, sans-serif; font-size: 14px; line-height: 1.5; }
  #textBox:focus { outline: 2px solid #5a8fd6; outline-offset: -1px; }
  #textBox pre { margin: 0 0 12px 0; white-space: pre-wrap; font-family: inherit; font-size: inherit; }
  #textBox .detected-table { border-collapse: collapse; margin: 8px 0 14px 0; font-size: 13px; width: 100%; }
  #textBox .detected-table th, #textBox .detected-table td { border: 1px solid #999; padding: 5px 8px; text-align: left; }
  #textBox .detected-table th { background: #ddd6c0; }
  #textBox .detected-table tr:nth-child(even) td { background: #eae7db; }
  .actions { margin-top: 10px; display: flex; gap: 8px; align-items: center; }
  .actions button { background: #2d5a2d; color: #fff; border: none; border-radius: 4px; padding: 8px 14px; cursor: pointer; }
  .actions button.download { background: #3a3a5a; }
  .status { font-size: 12px; color: #8f8; }
  .meta { margin-top: 14px; font-size: 12px; color: #aaa; background: #222; border-radius: 4px; padding: 10px; white-space: pre-wrap; }
  .hazard { color: #ffb347; }
  .warning { margin-top: 10px; font-size: 12px; color: #ffb347; background: #3a2f1a; border: 1px solid #5a4a2a; border-radius: 4px; padding: 8px 10px; display: none; }
</style>
</head>
<body>
<header>
  <h1>Document __DOCUMENT_ID__ - Page Review</h1>
  <button onclick="changePage(-1)">&larr; Prev</button>
  <input id="pageInput" type="number" min="1" value="1" onchange="loadPage(parseInt(this.value))">
  <span id="pageCount"></span>
  <button onclick="changePage(1)">Next &rarr;</button>
</header>
<div class="main">
  <div class="pane">
    <img id="pageImage" src="">
  </div>
  <div class="pane">
    <div class="warning" id="truncationWarning">Warning: this page's transcription looks incomplete (cuts off mid-sentence/mid-table) even after automatic retries. Please check against the image and correct if needed.</div>
    <div id="textBox" contenteditable="true"></div>
    <div class="actions">
      <button onclick="saveCorrection()">Save Correction</button>
      <button class="download" onclick="downloadText()">Download .txt</button>
      <span class="status" id="status"></span>
    </div>
    <div class="meta" id="meta"></div>
  </div>
</div>
<script>
const documentId = __DOCUMENT_ID__;
let currentPage = 1;
let pageCount = 1;

async function init() {
  const res = await fetch(`/api/review/${documentId}/pages`);
  const data = await res.json();
  pageCount = data.page_count || 1;
  document.getElementById('pageCount').textContent = `of ${pageCount}`;
  loadPage(1);
}

function changePage(delta) {
  const next = currentPage + delta;
  if (next < 1 || next > pageCount) return;
  loadPage(next);
}

async function loadPage(pageNum) {
  currentPage = pageNum;
  document.getElementById('pageInput').value = pageNum;
  document.getElementById('status').textContent = '';
  document.getElementById('pageImage').src = `/api/review/${documentId}/${pageNum}/image`;

  const res = await fetch(`/api/review/${documentId}/${pageNum}`);
  const data = await res.json();

  // rendered_html is server-built from a trusted source (this project's own
  // page_extractions/table_parser.py output, html.escape()'d cell-by-cell on
  // the way in) - safe to set directly, not user-supplied HTML. This IS the
  // OCR view - a real editable <table> for detected rows, not a separate
  // read-only copy next to a plain-text box.
  document.getElementById('textBox').innerHTML = data.rendered_html || '<pre>(no extraction yet)</pre>';

  let meta = '';
  if (data.header_fields) {
    meta += 'PASS 1 HEADER FIELDS:\\n';
    for (const [key, [value, confidence]] of Object.entries(data.header_fields)) {
      meta += `  ${key}: ${JSON.stringify(value)} [${confidence}]\\n`;
    }
    meta += '\\n';
  }
  meta += `HAZARDS ON THIS PAGE: ${data.hazards.length}\\n`;
  for (const h of data.hazards) {
    meta += `  - ${h.hazard_type} @ ${h.depth_m}m [${h.confidence} confidence, ${h.severity} severity]\\n`;
  }
  if (data.corrected_text) {
    meta += '\\n(showing your saved correction, not the original model output)';
  }
  document.getElementById('meta').textContent = meta;

  document.getElementById('truncationWarning').style.display = data.text_possibly_truncated ? 'block' : 'none';
}

// Converts the editable box's current DOM (real <table> elements included)
// back into a single plain-text string for saving - the inverse of the
// server's render_page_as_html(). A <table> becomes markdown pipe rows
// (matching table_parser.py's own to_markdown_table format, so re-opening
// this saved text still round-trips through the table detector correctly).
// Recurses into any element that CONTAINS a table (rather than only
// checking direct children) so an unusual DOM restructure from browser
// editing (e.g. everything getting wrapped in one new <div> after a
// select-all retype) still finds and correctly serializes a nested table,
// instead of silently flattening it to unstructured text via textContent.
function serializeEditableContent(container) {
  const lines = [];
  function walk(node) {
    if (node.nodeType === Node.TEXT_NODE) {
      if (node.textContent) lines.push(node.textContent);
      return;
    }
    if (node.nodeName === 'TABLE') {
      const rows = Array.from(node.querySelectorAll('tr'));
      rows.forEach((tr, idx) => {
        const cells = Array.from(tr.children).map((cell) => cell.textContent.trim());
        lines.push('| ' + cells.join(' | ') + ' |');
        if (idx === 0) {
          lines.push('| ' + cells.map(() => '---').join(' | ') + ' |');
        }
      });
      lines.push('');
      return;
    }
    if (node.nodeName === 'BR') {
      lines.push('');
      return;
    }
    if (typeof node.querySelector === 'function' && node.querySelector('table')) {
      for (const child of node.childNodes) walk(child);
      return;
    }
    const text = node.textContent;
    if (text) lines.push(text);
  }
  for (const child of container.childNodes) walk(child);
  return lines.join('\\n').replace(/\\n{3,}/g, '\\n\\n').trim();
}

async function saveCorrection() {
  const text = serializeEditableContent(document.getElementById('textBox'));
  const res = await fetch(`/api/review/${documentId}/${currentPage}/correction`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({text}),
  });
  document.getElementById('status').textContent = res.ok ? 'Saved.' : 'Save failed.';
}

function downloadText() {
  window.location = `/api/review/${documentId}/${currentPage}/download`;
}

init();
</script>
</body>
</html>
"""
