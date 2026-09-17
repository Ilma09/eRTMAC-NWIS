
"""
database.py
SQLite schema setup and CRUD functions.
Tables: wells, npt_hazards, documents, image_artifacts
(matches the schema specified in the eRTMAC-NWIS architecture doc, section 5)
"""
 
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional
 
from src.config import DB_PATH
 
 
# ---------------------------------------------------------------------------
# CONNECTION HELPERS
# ---------------------------------------------------------------------------
@contextmanager
def get_connection():
    """Yields a SQLite connection with foreign keys enabled and row access by column name."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
 
 
# ---------------------------------------------------------------------------
# SCHEMA INITIALIZATION
# ---------------------------------------------------------------------------
def init_db():
    """Creates all tables if they don't already exist. Safe to call on every startup."""
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents (
                document_id     INTEGER PRIMARY KEY AUTOINCREMENT,
                filename        TEXT NOT NULL,
                doc_type        TEXT,                     -- 'WCR' or 'DDR'
                file_path       TEXT NOT NULL,             -- path to original uploaded PDF
                file_hash       TEXT,                      -- SHA-256 of the uploaded file, for dedup
                well_id         INTEGER,                   -- which well this document is about (nullable:
                                                             -- unknown until Pass 1 parses it, or dedup links it)
                page_count      INTEGER,
                status          TEXT DEFAULT 'PROCESSING', -- PROCESSING | COMPLETE | NEEDS_REVIEW | FAILED
                uploaded_at     TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (well_id) REFERENCES wells(well_id)
            );
 
            CREATE TABLE IF NOT EXISTS wells (
                well_id         INTEGER PRIMARY KEY AUTOINCREMENT,
                well_name       TEXT NOT NULL,
                operator        TEXT,
                latitude        REAL,                      -- nullable: some real WCRs omit coordinates
                longitude       REAL,
                location_verified INTEGER DEFAULT 0,       -- 0/1: 1 only if extracted at HIGH confidence
                total_depth_m   REAL,
                well_type       TEXT,                      -- descriptive, extracted as-is: "Oil Producer" etc.
                field_location  TEXT,                      -- descriptive place name, e.g. "Ankleshwar Extension, Gujarat"
                status          TEXT DEFAULT 'ACTIVE',     -- lifecycle, derived not extracted: ACTIVE | PLUGGED | SUSPENDED | UNKNOWN
                document_id     INTEGER,
                file_path       TEXT,                      -- relative path to source PDF
                created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (document_id) REFERENCES documents(document_id)
            );
 
            CREATE TABLE IF NOT EXISTS npt_hazards (
                hazard_id       INTEGER PRIMARY KEY AUTOINCREMENT,
                well_id         INTEGER NOT NULL,
                hazard_type     TEXT,                      -- Stuck Pipe, Lost Circulation, Gas Kick, etc.
                depth_m         REAL NOT NULL,
                confidence      TEXT DEFAULT 'LOW',        -- HIGH | MEDIUM | LOW, legibility of the depth reading
                severity        TEXT,                      -- HIGH | CRITICAL | MEDIUM
                page_num        INTEGER,
                description     TEXT,
                FOREIGN KEY (well_id) REFERENCES wells(well_id)
            );
 
            CREATE TABLE IF NOT EXISTS image_artifacts (
                artifact_id     INTEGER PRIMARY KEY AUTOINCREMENT,
                well_id         INTEGER,
                document_id     INTEGER,
                page_num        INTEGER,
                artifact_type   TEXT,                      -- Lithology Chart, Casing Diagram, Full Page, etc.
                artifact_kind   TEXT DEFAULT 'PAGE_RENDER', -- 'PAGE_RENDER' | 'EMBEDDED_FIGURE' - structural
                                                             -- category, separate from the descriptive artifact_type
                bbox_x0         REAL,                       -- page-pixel bounding box, NULL for PAGE_RENDER
                bbox_y0         REAL,
                bbox_x1         REAL,
                bbox_y1         REAL,
                width           INTEGER,                    -- saved image file's pixel dimensions
                height          INTEGER,
                file_path       TEXT NOT NULL,
                created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (well_id) REFERENCES wells(well_id),
                FOREIGN KEY (document_id) REFERENCES documents(document_id)
            );

            CREATE TABLE IF NOT EXISTS page_extractions (
                document_id     INTEGER NOT NULL,
                page_num        INTEGER NOT NULL,
                page_text       TEXT,                      -- Pass 2 transcription, empty string if parse failed
                parse_ok        INTEGER,                   -- Pass 2 parse_ok (0/1) - NOT "no hazards found"
                header_fields   TEXT,                      -- JSON {field: {value, confidence}}, NULL if this
                                                             -- page wasn't in Pass 1's scope (pages 3+)
                corrected_text  TEXT,                      -- human correction, SEPARATE from page_text -
                                                             -- the original VLM output is never overwritten
                extracted_at    TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (document_id, page_num),
                FOREIGN KEY (document_id) REFERENCES documents(document_id)
            );

            CREATE INDEX IF NOT EXISTS idx_hazards_well_depth ON npt_hazards(well_id, depth_m);
            CREATE INDEX IF NOT EXISTS idx_wells_location ON wells(latitude, longitude);
            """
        )
    migrate_schema()


def _table_columns(conn, table_name: str) -> set:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def migrate_schema():
    """
    Additive migration for databases created before the nullable-coordinates /
    confidence-tracking schema change. CREATE TABLE IF NOT EXISTS above only
    applies to brand-new databases - an existing data/app.db (e.g. from
    test_setup.py's earlier run) keeps its original column set until migrated.
    Safe to call repeatedly.
    """
    with get_connection() as conn:
        doc_cols = _table_columns(conn, "documents")
        if "file_hash" not in doc_cols:
            conn.execute("ALTER TABLE documents ADD COLUMN file_hash TEXT")
        if "well_id" not in doc_cols:
            conn.execute("ALTER TABLE documents ADD COLUMN well_id INTEGER REFERENCES wells(well_id)")

        hazard_cols = _table_columns(conn, "npt_hazards")
        if "confidence" not in hazard_cols:
            conn.execute("ALTER TABLE npt_hazards ADD COLUMN confidence TEXT DEFAULT 'LOW'")

        well_cols = _table_columns(conn, "wells")
        if "location_verified" not in well_cols:
            conn.execute("ALTER TABLE wells ADD COLUMN location_verified INTEGER DEFAULT 0")
        if "well_type" not in well_cols:
            conn.execute("ALTER TABLE wells ADD COLUMN well_type TEXT")
        if "field_location" not in well_cols:
            conn.execute("ALTER TABLE wells ADD COLUMN field_location TEXT")
        # Both derived the same way as well lifecycle status (derive_well_status) -
        # keyword/regex rules over already-transcribed page text, NOT a new VLM
        # call. Deliberately kept out of the image-based Pass 1/Pass 2 extraction
        # entirely, since that pipeline is already tight on VRAM/output-length
        # budget (see MAX_RENDER_DIMENSION_PX and VLM_NUM_CTX_PASS2 in config.py) -
        # adding more fields there would make real, already-observed failures
        # worse, not better.
        if "formation" not in well_cols:
            conn.execute("ALTER TABLE wells ADD COLUMN formation TEXT")
        if "mud_type" not in well_cols:
            conn.execute("ALTER TABLE wells ADD COLUMN mud_type TEXT")
        # Same derivation method as formation/mud_type above (regex over
        # already-transcribed text) - added to cover the remaining PS
        # correlation parameters (drilling parameters, reservoir
        # characteristics, casing programs, cementing practices). Each is
        # free text (a captured label:value snippet), not a fully parsed
        # structured field - a pragmatic choice given these often appear as
        # multi-row tables that a simple regex can't safely decompose, per
        # unified_parser.derive_well_enrichment's docstring.
        if "mud_weight" not in well_cols:
            conn.execute("ALTER TABLE wells ADD COLUMN mud_weight TEXT")
        if "casing_notes" not in well_cols:
            conn.execute("ALTER TABLE wells ADD COLUMN casing_notes TEXT")
        if "cementing_notes" not in well_cols:
            conn.execute("ALTER TABLE wells ADD COLUMN cementing_notes TEXT")
        if "reservoir_notes" not in well_cols:
            conn.execute("ALTER TABLE wells ADD COLUMN reservoir_notes TEXT")

        page_extraction_cols = _table_columns(conn, "page_extractions")
        if "corrected_text" not in page_extraction_cols:
            conn.execute("ALTER TABLE page_extractions ADD COLUMN corrected_text TEXT")
        # Lets a hard-failed page (parse_ok=0) carry a short explanation of WHY
        # it failed (e.g. GPU memory pressure vs. unparseable output) - see
        # unified_parser._call_and_parse's failure_reason. Before this column
        # existed, a failed page's row had no failure detail anywhere, and the
        # Corpus UI's status badge didn't check parse_ok at all - a hard-failed
        # page could show a misleading "Extracted" badge with no explanation.
        if "failure_reason" not in page_extraction_cols:
            conn.execute("ALTER TABLE page_extractions ADD COLUMN failure_reason TEXT")

        artifact_cols = _table_columns(conn, "image_artifacts")
        if "artifact_kind" not in artifact_cols:
            conn.execute("ALTER TABLE image_artifacts ADD COLUMN artifact_kind TEXT DEFAULT 'PAGE_RENDER'")
        if "bbox_x0" not in artifact_cols:
            conn.execute("ALTER TABLE image_artifacts ADD COLUMN bbox_x0 REAL")
        if "bbox_y0" not in artifact_cols:
            conn.execute("ALTER TABLE image_artifacts ADD COLUMN bbox_y0 REAL")
        if "bbox_x1" not in artifact_cols:
            conn.execute("ALTER TABLE image_artifacts ADD COLUMN bbox_x1 REAL")
        if "bbox_y1" not in artifact_cols:
            conn.execute("ALTER TABLE image_artifacts ADD COLUMN bbox_y1 REAL")
        if "width" not in artifact_cols:
            conn.execute("ALTER TABLE image_artifacts ADD COLUMN width INTEGER")
        if "height" not in artifact_cols:
            conn.execute("ALTER TABLE image_artifacts ADD COLUMN height INTEGER")
        if "created_at" not in artifact_cols:
            conn.execute("ALTER TABLE image_artifacts ADD COLUMN created_at TEXT DEFAULT CURRENT_TIMESTAMP")

        # latitude/longitude NOT NULL can't be dropped via ALTER TABLE in SQLite -
        # requires the standard rebuild-copy-rename dance. Only run it if the old
        # NOT NULL constraint is still present (idempotent, safe to call repeatedly).
        lat_info = next(
            row for row in conn.execute("PRAGMA table_info(wells)").fetchall() if row["name"] == "latitude"
        )
        if lat_info["notnull"]:
            conn.executescript(
                """
                CREATE TABLE wells_new (
                    well_id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    well_name       TEXT NOT NULL,
                    operator        TEXT,
                    latitude        REAL,
                    longitude       REAL,
                    location_verified INTEGER DEFAULT 0,
                    total_depth_m   REAL,
                    well_type       TEXT,
                    field_location  TEXT,
                    status          TEXT DEFAULT 'ACTIVE',
                    document_id     INTEGER,
                    file_path       TEXT,
                    created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (document_id) REFERENCES documents(document_id)
                );
                INSERT INTO wells_new
                    (well_id, well_name, operator, latitude, longitude, location_verified,
                     total_depth_m, well_type, field_location, status, document_id, file_path, created_at)
                SELECT well_id, well_name, operator, latitude, longitude,
                       COALESCE(location_verified, 0),
                       total_depth_m, well_type, field_location, status, document_id, file_path, created_at
                FROM wells;
                DROP TABLE wells;
                ALTER TABLE wells_new RENAME TO wells;
                CREATE INDEX IF NOT EXISTS idx_wells_location ON wells(latitude, longitude);
                """
            )


# ---------------------------------------------------------------------------
# DOCUMENTS CRUD
# ---------------------------------------------------------------------------
def create_document(
    filename: str, doc_type: str, file_path: str, page_count: int, file_hash: Optional[str] = None
) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO documents (filename, doc_type, file_path, file_hash, page_count, status) "
            "VALUES (?, ?, ?, ?, ?, 'PROCESSING')",
            (filename, doc_type, file_path, file_hash, page_count),
        )
        return cur.lastrowid


def find_document_by_hash(file_hash: str) -> Optional[dict]:
    """Dedup check: an identical file already ingested has the same SHA-256 hash."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM documents WHERE file_hash = ?", (file_hash,)
        ).fetchone()
        return dict(row) if row else None
 
 
def update_document_status(document_id: int, status: str):
    with get_connection() as conn:
        conn.execute(
            "UPDATE documents SET status = ? WHERE document_id = ?", (status, document_id)
        )


def link_document_to_well(document_id: int, well_id: int):
    """Records which well a document is about. One well can have many documents
    over its lifetime (WCR now, DDR later) - the FK lives here on documents, not
    as a single wells.document_id pointer, so linking a second document never
    displaces the first."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE documents SET well_id = ? WHERE document_id = ?", (well_id, document_id)
        )
 
 
def list_documents():
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM documents ORDER BY uploaded_at DESC").fetchall()
        return [dict(r) for r in rows]
 
 
def get_document(document_id: int) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM documents WHERE document_id = ?", (document_id,)
        ).fetchone()
        return dict(row) if row else None


def delete_document(document_id: int) -> Optional[int]:
    """Deletes a document and everything scoped to it (page_extractions,
    image_artifacts). Returns the well_id it was linked to (if any) so the
    caller can decide whether to also remove that well - a well can have
    more than one document linked to it (see link_document_to_well's dedup-
    by-name path), so deleting the well is NOT this function's job; it would
    silently destroy a still-valid well backed by a different document."""
    with get_connection() as conn:
        row = conn.execute("SELECT well_id FROM documents WHERE document_id = ?", (document_id,)).fetchone()
        if row is None:
            return None
        well_id = row["well_id"]
        conn.execute("DELETE FROM page_extractions WHERE document_id = ?", (document_id,))
        conn.execute("DELETE FROM image_artifacts WHERE document_id = ?", (document_id,))
        # wells.document_id is a foreign key into documents - a well records
        # which document originally created it, but that's informational
        # (nullable), not the well's identity. Clear it rather than leave a
        # dangling reference, or the next DELETE violates the FK constraint
        # (reproduced directly: deleting a document whose well still pointed
        # at it raised sqlite3.IntegrityError).
        conn.execute("UPDATE wells SET document_id = NULL WHERE document_id = ?", (document_id,))
        conn.execute("DELETE FROM documents WHERE document_id = ?", (document_id,))
        return well_id


def count_documents_for_well(well_id: int) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM documents WHERE well_id = ?", (well_id,)
        ).fetchone()
        return row["c"]


def delete_well(well_id: int) -> None:
    """Deletes a well and its hazards. Only safe to call once the caller has
    confirmed no document still references this well (see delete_document +
    count_documents_for_well) - this function itself does not check, so a
    stray document row would be left pointing at a well_id that no longer
    exists."""
    with get_connection() as conn:
        conn.execute("DELETE FROM npt_hazards WHERE well_id = ?", (well_id,))
        conn.execute("DELETE FROM wells WHERE well_id = ?", (well_id,))


# ---------------------------------------------------------------------------
# WELLS CRUD
# ---------------------------------------------------------------------------
def create_well(
    well_name: str,
    operator: Optional[str],
    latitude: Optional[float],
    longitude: Optional[float],
    total_depth_m: Optional[float],
    document_id: Optional[int] = None,
    file_path: Optional[str] = None,
    status: str = "ACTIVE",
    location_verified: bool = False,
    well_type: Optional[str] = None,
    field_location: Optional[str] = None,
    formation: Optional[str] = None,
    mud_type: Optional[str] = None,
    mud_weight: Optional[str] = None,
    casing_notes: Optional[str] = None,
    cementing_notes: Optional[str] = None,
    reservoir_notes: Optional[str] = None,
) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO wells
               (well_name, operator, latitude, longitude, location_verified,
                total_depth_m, well_type, field_location, status, document_id,
                file_path, formation, mud_type, mud_weight, casing_notes,
                cementing_notes, reservoir_notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                well_name,
                operator,
                latitude,
                longitude,
                int(location_verified),
                total_depth_m,
                well_type,
                field_location,
                status,
                document_id,
                file_path,
                formation,
                mud_type,
                mud_weight,
                casing_notes,
                cementing_notes,
                reservoir_notes,
            ),
        )
        return cur.lastrowid


def find_well_by_name(well_name: str) -> Optional[dict]:
    """Dedup check: case-insensitive, trimmed match - a well legitimately gets
    multiple documents over its lifetime (WCR now, DDR later), so a name match
    should link the new document to the existing well rather than duplicate it."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM wells WHERE TRIM(LOWER(well_name)) = TRIM(LOWER(?))", (well_name,)
        ).fetchone()
        return dict(row) if row else None


def list_wells():
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM wells ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]
 
 
def get_well(well_id: int) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM wells WHERE well_id = ?", (well_id,)).fetchone()
        return dict(row) if row else None


def update_well_status(well_id: int, status: str) -> None:
    """Updates the derived lifecycle status (ACTIVE/PLUGGED/SUSPENDED) after
    re-deriving it from a fuller set of page texts than was available the
    first time - see unified_parser.resume_extraction()."""
    with get_connection() as conn:
        conn.execute("UPDATE wells SET status = ? WHERE well_id = ?", (status, well_id))


def update_well_enrichment(
    well_id: int,
    formation: Optional[str],
    mud_type: Optional[str],
    mud_weight: Optional[str] = None,
    casing_notes: Optional[str] = None,
    cementing_notes: Optional[str] = None,
    reservoir_notes: Optional[str] = None,
) -> None:
    """Backfills derived well-comparison fields onto an already-created well -
    used by the one-off enrichment script for wells ingested before these
    fields existed. Only overwrites a field when a new (non-None) value was
    found, so re-running the backfill never blanks out a value it already set."""
    with get_connection() as conn:
        if formation is not None:
            conn.execute("UPDATE wells SET formation = ? WHERE well_id = ?", (formation, well_id))
        if mud_type is not None:
            conn.execute("UPDATE wells SET mud_type = ? WHERE well_id = ?", (mud_type, well_id))
        if mud_weight is not None:
            conn.execute("UPDATE wells SET mud_weight = ? WHERE well_id = ?", (mud_weight, well_id))
        if casing_notes is not None:
            conn.execute("UPDATE wells SET casing_notes = ? WHERE well_id = ?", (casing_notes, well_id))
        if cementing_notes is not None:
            conn.execute("UPDATE wells SET cementing_notes = ? WHERE well_id = ?", (cementing_notes, well_id))
        if reservoir_notes is not None:
            conn.execute("UPDATE wells SET reservoir_notes = ? WHERE well_id = ?", (reservoir_notes, well_id))

 
def count_wells(active_only: bool = False) -> int:
    with get_connection() as conn:
        if active_only:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM wells WHERE status = 'ACTIVE'"
            ).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) AS c FROM wells").fetchone()
        return row["c"]
 
 
# ---------------------------------------------------------------------------
# NPT HAZARDS CRUD
# ---------------------------------------------------------------------------
def create_hazard(
    well_id: int,
    hazard_type: str,
    depth_m: float,
    confidence: str,
    severity: Optional[str],
    page_num: Optional[int],
    description: Optional[str] = None,
) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO npt_hazards
               (well_id, hazard_type, depth_m, confidence, severity, page_num, description)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (well_id, hazard_type, depth_m, confidence, severity, page_num, description),
        )
        return cur.lastrowid
 
 
def get_hazards_for_well(well_id: int):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM npt_hazards WHERE well_id = ? ORDER BY depth_m", (well_id,)
        ).fetchall()
        return [dict(r) for r in rows]
 
 
def find_hazards_in_depth_window(well_ids: list[int], target_depth_m: float, window_m: float):
    """Returns hazards for the given wells within +/- window_m of target_depth_m.

    Filters to confidence IN (HIGH, MEDIUM) directly in SQL - per the design
    decision, a LOW-confidence hazard reading is stored (never discarded) but
    must never participate in live alerting until a human reviews and upgrades
    it. See hazard_monitor.py, the only intended caller of this function."""
    if not well_ids:
        return []
    with get_connection() as conn:
        placeholders = ",".join("?" for _ in well_ids)
        query = f"""
            SELECT h.*, w.well_name, w.latitude, w.longitude
            FROM npt_hazards h
            JOIN wells w ON h.well_id = w.well_id
            WHERE h.well_id IN ({placeholders})
              AND ABS(h.depth_m - ?) <= ?
              AND h.confidence IN ('HIGH', 'MEDIUM')
            ORDER BY ABS(h.depth_m - ?) ASC
        """
        rows = conn.execute(
            query, (*well_ids, target_depth_m, window_m, target_depth_m)
        ).fetchall()
        return [dict(r) for r in rows]
 
 
def count_hazards() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM npt_hazards").fetchone()
        return row["c"]
 
 
# ---------------------------------------------------------------------------
# IMAGE ARTIFACTS CRUD
# ---------------------------------------------------------------------------
def create_image_artifact(
    well_id: Optional[int],
    document_id: Optional[int],
    page_num: int,
    artifact_type: str,
    file_path: str,
    artifact_kind: str = "PAGE_RENDER",
    bbox: Optional[tuple] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
) -> int:
    """
    artifact_kind: 'PAGE_RENDER' (default, matches every existing call site -
    full-page renders) or 'EMBEDDED_FIGURE' (figure_extractor.py's cropped
    figures). bbox: optional (x0, y0, x1, y1) in the page image's own pixel
    coordinates - meaningful for EMBEDDED_FIGURE, left None for PAGE_RENDER
    (the bbox there is trivially the whole image, not worth storing)."""
    bbox_x0, bbox_y0, bbox_x1, bbox_y1 = bbox if bbox is not None else (None, None, None, None)
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO image_artifacts
               (well_id, document_id, page_num, artifact_type, artifact_kind,
                bbox_x0, bbox_y0, bbox_x1, bbox_y1, width, height, file_path)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                well_id, document_id, page_num, artifact_type, artifact_kind,
                bbox_x0, bbox_y0, bbox_x1, bbox_y1, width, height, file_path,
            ),
        )
        return cur.lastrowid
 
 
def get_image_artifacts_for_document(document_id: int):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM image_artifacts WHERE document_id = ? ORDER BY page_num", (document_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def upsert_page_extraction(
    document_id: int,
    page_num: int,
    page_text: Optional[str] = None,
    parse_ok: Optional[bool] = None,
    header_fields_json: Optional[str] = None,
    failure_reason: Optional[str] = None,
) -> None:
    """Insert-or-replace, keyed by (document_id, page_num). Pass 1 (header
    fields) and Pass 2 (page_text/parse_ok/failure_reason) both touch pages
    1-2 - each call only carries the columns that pass is responsible for,
    leaving the rest as None, and COALESCE keeps whatever was already stored
    for the columns this call didn't touch rather than clobbering it (a naive
    REPLACE would let Pass 2's call erase Pass 1's header_fields on the same
    page, or vice versa).

    failure_reason is NOT coalesced like the others - it's tied to parse_ok
    (both always come from the same Pass 2 call, never independently from
    Pass 1) and must be allowed to go from a stale string back to NULL when a
    later retry/resume succeeds where an earlier attempt on the same page
    failed. The CASE below only touches failure_reason when this call is
    actually carrying a parse_ok (i.e. a real Pass 2 result), leaving it
    untouched on a Pass-1-only call."""
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO page_extractions (document_id, page_num, page_text, parse_ok, header_fields, failure_reason)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(document_id, page_num) DO UPDATE SET
                   page_text = COALESCE(excluded.page_text, page_extractions.page_text),
                   parse_ok = COALESCE(excluded.parse_ok, page_extractions.parse_ok),
                   header_fields = COALESCE(excluded.header_fields, page_extractions.header_fields),
                   failure_reason = CASE WHEN excluded.parse_ok IS NOT NULL
                                         THEN excluded.failure_reason
                                         ELSE page_extractions.failure_reason END,
                   extracted_at = CURRENT_TIMESTAMP""",
            (
                document_id,
                page_num,
                page_text,
                None if parse_ok is None else int(parse_ok),
                header_fields_json,
                failure_reason,
            ),
        )


def get_page_extractions_for_document(document_id: int):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM page_extractions WHERE document_id = ? ORDER BY page_num", (document_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_page_extraction(document_id: int, page_num: int) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM page_extractions WHERE document_id = ? AND page_num = ?",
            (document_id, page_num),
        ).fetchone()
        return dict(row) if row else None


def save_corrected_text(document_id: int, page_num: int, corrected_text: str) -> None:
    """Human review correction - kept in its own column, never overwrites the
    original page_text. Requires the row already exist (from an extraction
    run); does nothing if it doesn't, rather than creating a partial row."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE page_extractions SET corrected_text = ? WHERE document_id = ? AND page_num = ?",
            (corrected_text, document_id, page_num),
        )


def count_documents() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM documents").fetchone()
        return row["c"]
 
