"""
config.py
Central configuration for eRTMAC-NWIS backend.
Holds paths, spatial/vertical thresholds, and model identifiers.
All other modules import from here instead of hardcoding values.
"""
 
import os
from pathlib import Path
 
# ---------------------------------------------------------------------------
# BASE PATHS
# ---------------------------------------------------------------------------
# BASE_DIR = the "backend/" folder itself, regardless of where scripts are run from
BASE_DIR = Path(__file__).resolve().parent.parent
 
PAGES_DIR = BASE_DIR / "pages"                  # full-page rasterized PNGs (pdf_processor.py's output) -
                                                 # was ARTIFACTS_DIR before the artifacts/ rename; renamed
                                                 # because artifacts/ now means something different (below)
ARTIFACTS_DIR = BASE_DIR / "artifacts"          # embedded figures/charts extracted FROM WITHIN a page's
                                                 # content (see src/figure_extractor.py) - NOT full-page
                                                 # renders, that's PAGES_DIR's job
DATA_DIR = BASE_DIR / "data"                    # SQLite db + Qdrant storage
UPLOADS_DIR = BASE_DIR / "uploads"              # raw uploaded PDFs (original files)

DB_PATH = DATA_DIR / "app.db"                   # SQLite database file
QDRANT_PATH = DATA_DIR / "qdrant_db"            # embedded Qdrant on-disk storage

# Create directories on import if they don't exist yet (safe, idempotent)
for _dir in (PAGES_DIR, ARTIFACTS_DIR, DATA_DIR, UPLOADS_DIR, QDRANT_PATH):
    _dir.mkdir(parents=True, exist_ok=True)
 
# ---------------------------------------------------------------------------
# PDF RASTERIZATION SETTINGS
# ---------------------------------------------------------------------------
RENDER_DPI = 200          # 200 DPI = crisp text, manageable file size (per spec)
PDF_IMAGE_FORMAT = "png"  # lossless, required for legibility of fine well-log text

# Caps the LONGER side of a rendered page in pixels, regardless of RENDER_DPI -
# found necessary against real data, not assumed: document_id=17's source PDF
# has a genuinely oversized physical page (19.3in x 25in, not letter/A4), so a
# flat 200 DPI render produced a 3864x5000 (~19 megapixel) image. Verified
# directly that Ollama fails (done=False, the same VRAM-pressure signature
# documented elsewhere in this project) on that size but succeeds reliably
# once capped down near this value. Pages within normal physical dimensions
# (the vast majority) are unaffected - this only kicks in when a page would
# otherwise exceed it.
MAX_RENDER_DIMENSION_PX = 2200
 
# ---------------------------------------------------------------------------
# HAZARD MONITOR THRESHOLDS (per PDF spec section 4, Layer 3)
# ---------------------------------------------------------------------------
SEARCH_RADIUS_KM = 10.0    # surface geodesic distance cutoff for "nearby" wells
DEPTH_WINDOW_M = 50.0      # vertical window for hazard correlation
 
# ---------------------------------------------------------------------------
# MODEL CONFIGURATION
# ---------------------------------------------------------------------------
# Vision-Language Model served locally via Ollama
#
# KNOWN ISSUE: Ollama's own background auto-updater can silently kill the running
# server mid-session (observed directly during development - a batch of test calls
# started failing with a raw connection-refused error because Ollama had launched
# OllamaSetup.exe on its own and torn down the server process). Before any
# long-running batch operation (e.g. full document ingestion across many pages),
# confirm `ollama list` responds, and consider disabling Ollama's auto-update
# setting for the duration of active development. This is a real risk during a
# live demo if it triggers mid-upload. See src/utils.py's call_ollama_chat(),
# which classifies a connection-refused failure explicitly instead of surfacing
# a generic httpx traceback.
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
VLM_MODEL_NAME = "qwen2.5vl:3b"

# Context window sizes, verified against real Ollama calls (see test_vlm_extraction.py
# and test_vlm_pass2_ctx.py) rather than assumed. The default Ollama context (4096)
# is NOT enough to hold one 200 DPI page image - it undercounts by ~200 tokens even
# for a 5-field header extraction.
# Pass 1 (header fields only): measured 4317 prompt tokens on a real page -> 8192 fits
# with comfortable margin.
VLM_NUM_CTX_PASS1 = 8192
# Pass 2 (full page text transcription + hazard extraction): measured 4780 total
# tokens (4243 prompt + 537 output) on a note-dense real page. Originally set to
# 12288 for headroom on denser pages, but verified directly that this was wrong:
# num_ctx pre-allocates VRAM for the WHOLE context window regardless of tokens
# actually used, and 12288 pushed this 4GB card to 3947/4096 MiB used - at that
# point generation started failing mid-stream (a "done": false partial response
# with none of the normal completion metadata, no exception raised) instead of
# erroring cleanly. Reproduced twice, fixed by dropping back to 8192, confirmed
# by a `done: True` complete response afterward. 8192 still gives ~1.7x headroom
# over the 4780 measured, which matches what Pass 1 already uses successfully -
# do not raise this again without measuring actual VRAM headroom on this card,
# not just token counts.
VLM_NUM_CTX_PASS2 = 8192
 
# Dense embedding model (runs on CPU via sentence-transformers)
EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384        # bge-small output dimension (must match Qdrant collection config)
 
# Qdrant collection name
QDRANT_COLLECTION_NAME = "nwis_page_chunks"
 
# RAG retrieval settings
RAG_TOP_K = 3              # number of chunks retrieved per query (per spec)
 
# ---------------------------------------------------------------------------
# CORS / API SETTINGS (used by main.py)
# ---------------------------------------------------------------------------
FRONTEND_DEV_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
 
