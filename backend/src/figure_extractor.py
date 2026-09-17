"""
figure_extractor.py
Detects and crops embedded figures/diagrams/charts out of an already-rendered
page PNG (see pages/, pdf_processor.py) using classical document layout
analysis - projection/connected-component shape heuristics, NOT a trained
model. See the Task 2 investigation this was built from: a pretrained
layout-detection model (Detectron2/LayoutParser-style) was rejected in favor
of this heuristic because it would add a second model competing for VRAM on
a system already tight at 4GB, and asking the VLM itself for bounding boxes
was rejected as untested/unverified spatial-grounding reliability through a
generic chat API. This approach adds zero new heavy dependencies (just
OpenCV, pure CPU) and zero extra VLM calls - it never touches _VLM_LOCK.

WHAT THIS DOES NOT DO, by design, not oversight: this is purely visual - it
operates on the rendered PNG's pixels only, has no access to and does not
feed unified_parser.py's text/hazard extraction, vector_store.py's indexing,
or hazard_monitor.py's correlation. A detected figure is stored as a
standalone image in ARTIFACTS_DIR (distinct from PAGES_DIR's full-page
renders) purely for later human/frontend viewing - nothing inside a detected
figure becomes searchable text or a hazard record.

ALGORITHM (classical layout analysis, not ML):
 1. Grayscale + Otsu threshold -> binary ink/background image.
 2. Morphological dilation merges individual glyphs into words/lines and,
    for line-art/photos, into one large connected blob - this is what makes
    the next step able to tell "many thin evenly-spaced strips" (text) apart
    from "one big irregular blob" (a figure).
 3. Connected-component analysis over the dilated image finds candidate
    blobs.
 4. Each candidate is filtered by:
    - minimum area fraction (reject stray marks/punctuation)
    - maximum page-coverage (reject anything close to the whole page - this
      is what stops a full-page scan, or a badly degraded page, from being
      misread as "one giant figure" - the same purpose the coverage filter
      served in the pypdfium2 object-extraction investigation)
    - aspect ratio bounds (reject razor-thin slivers - stray rule lines are
      not figures)
    - internal row-density regularity (_looks_like_text_block) - a candidate
      that still shows the evenly-spaced-peaks signature of text lines even
      after dilation is a dense text/table block, not a figure, and is
      rejected regardless of size.

LIMITATION, verified directly rather than assumed: validated against the
Gujarat WCR sample's real pages (pages/TESTDOC_p1..5). Pages 1-3 (pure
prose) correctly produced zero false positives. Pages 4 and 5 each produced
one real false positive: page 4's is a short (3-line) bold-emphasized text
paragraph - too few lines for _looks_like_text_block's periodicity check to
confidently call it "text" (that check needs several line-bands to
establish regularity; a very short block is genuinely ambiguous by this
method). Page 5's is the cementing-parameters TABLE, misread as a figure.

A grid-line detector (morphological opening with long thin horizontal/
vertical kernels, meant to catch ruled table borders specifically) was
tried and tested directly against this exact false positive before being
rejected: it did NOT discriminate the real table (3.1% grid-line coverage)
from the real embedded figures (0.1-3.6% coverage) or plain text (0%) -
this sample's table borders are too faint/thin after Otsu thresholding on a
degraded scan to produce a distinctly stronger signal than incidental line
fragments elsewhere. Not pursued further past that direct test - chasing
higher precision here would cost more tuning time than the false-positive
rate justifies, given the accepted mitigation below.

Both false-positive classes (short bold text, ruled tables on degraded
scans) are accepted rather than chased further, same reasoning as every
other heuristic limitation in this project: backstopped by the existing
human-review workflow (routers/review.py) rather than treated as
must-fix-before-shipping. A human looking at a wrongly-flagged "figure"
that's actually a table immediately recognizes it as such - low severity,
not a silent safety-relevant failure like a missed hazard would be.
"""
from typing import Dict, List, Tuple

import cv2
import numpy as np
from PIL import Image

from src.config import ARTIFACTS_DIR

# --- Tunable thresholds - starting values for 200 DPI page renders, meant to
# be tuned against real samples, not treated as final. ---
_DILATE_KERNEL_SIZE = (25, 15)      # (width, height) px - merges glyphs into words/lines/blobs
_MIN_AREA_FRACTION = 0.01           # candidate smaller than 1% of the page = stray mark, not a figure
_MAX_AREA_FRACTION = 0.85           # candidate bigger than 85% of the page = probably the whole page
_MIN_ASPECT_RATIO = 0.15            # reject razor-thin slivers (stray rule lines, not figures)
_TEXT_DENSITY_ROW_THRESHOLD = 0.3   # row counted as "on" if its ink density exceeds this fraction of the row max
_TEXT_REGULARITY_FRACTION = 0.6     # fraction of gaps that must look line-spaced-regular to call it "text"


def _looks_like_text_block(binary_region: np.ndarray) -> bool:
    """
    Checks whether a candidate region's internal structure still looks like
    evenly-spaced text lines even after dilation - a real, dense text/table
    block does not stop looking like "many periodic horizontal bands" just
    because it's large enough to pass the area filter. Computes the row-wise
    ink density profile and checks whether the gaps between "on" bands are
    consistently similar (periodic), which is the signature of stacked text
    lines; a genuine figure's row-density profile does not show that
    regularity. Not a rigorous FFT-based periodicity test - a cheap proxy
    that is sufficient to separate the real samples this was validated
    against (see validate_figure_extractor.py).
    """
    if binary_region.size == 0:
        return False
    row_density = binary_region.sum(axis=1).astype(float)
    if row_density.max() == 0:
        return False
    row_density = row_density / row_density.max()

    on_rows = row_density > _TEXT_DENSITY_ROW_THRESHOLD
    transitions = np.diff(on_rows.astype(int))
    band_starts = np.where(transitions == 1)[0]
    if len(band_starts) < 3:
        return False  # too few bands to call "regular" one way or the other - let other filters decide
    gaps = np.diff(band_starts)
    if len(gaps) == 0:
        return False
    median_gap = np.median(gaps)
    if median_gap <= 0:
        return False
    regular = np.abs(gaps - median_gap) < (median_gap * 0.5)
    return bool(regular.mean() >= _TEXT_REGULARITY_FRACTION)


def _contains(outer: Tuple[int, int, int, int], inner: Tuple[int, int, int, int], margin: int = 5) -> bool:
    ox0, oy0, ox1, oy1 = outer
    ix0, iy0, ix1, iy1 = inner
    return ox0 - margin <= ix0 and oy0 - margin <= iy0 and ox1 + margin >= ix1 and oy1 + margin >= iy1


def _drop_container_boxes(candidates: List[Dict]) -> List[Dict]:
    """
    Removes a real, observed failure mode (verified directly against a
    research-PDF page with two genuinely separate embedded figures side by
    side): dilation can bridge the gap between two distinct visual elements
    (e.g. a paragraph of text sitting next to a real figure) into one
    over-merged "container" blob that spans both plus whatever sits between
    them. That container fails _looks_like_text_block (it's not pure text
    either) and would otherwise be saved as a bogus, bloated "figure" that
    duplicates the real figures already detected inside it.

    Rule: if one candidate's bbox fully contains 2 or more OTHER candidates'
    bboxes, it is almost certainly this kind of over-merge, not a genuine
    figure of its own - drop it and keep the smaller, precise ones. A
    container holding only 0-1 other candidates is left alone (could be a
    single genuine figure that happens to have a small sub-detection inside
    it, e.g. a legend box - not the failure pattern this targets).
    """
    keep = []
    for i, candidate in enumerate(candidates):
        contained_count = sum(
            1 for j, other in enumerate(candidates) if i != j and _contains(candidate["bbox"], other["bbox"])
        )
        if contained_count >= 2:
            continue
        keep.append(candidate)
    return keep


def extract_figures_from_page(image_path: str) -> List[Dict]:
    """
    Detects candidate figure regions in an already-rendered page PNG. Returns
    [{"bbox": (x0, y0, x1, y1), "image": PIL.Image (cropped, RGB)}, ...] -
    does not touch disk beyond reading image_path. See save_figures_for_page
    for the disk-writing wrapper, kept separate so this stays independently
    testable/inspectable (e.g. for tuning thresholds against real samples
    without generating files each time).
    """
    color_image = Image.open(image_path).convert("RGB")
    gray = np.array(color_image.convert("L"))
    page_h, page_w = gray.shape
    page_area = page_h * page_w

    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, _DILATE_KERNEL_SIZE)
    dilated = cv2.dilate(binary, kernel, iterations=1)

    num_labels, _labels, stats, _centroids = cv2.connectedComponentsWithStats(dilated, connectivity=8)

    candidates = []
    for label in range(1, num_labels):  # label 0 is the background component
        x, y, w, h, area = stats[label]
        coverage = area / page_area
        if coverage < _MIN_AREA_FRACTION or coverage > _MAX_AREA_FRACTION:
            continue
        aspect = min(w, h) / max(w, h) if max(w, h) > 0 else 0
        if aspect < _MIN_ASPECT_RATIO:
            continue

        region_binary = binary[y : y + h, x : x + w] > 0
        if _looks_like_text_block(region_binary):
            continue

        candidates.append(
            {
                "bbox": (int(x), int(y), int(x + w), int(y + h)),
                "image": color_image.crop((x, y, x + w, y + h)),
            }
        )
    return _drop_container_boxes(candidates)


def save_figures_for_page(image_path: str, doc_slug: str, page_num: int) -> List[Dict]:
    """
    Runs extract_figures_from_page and saves each surviving candidate as its
    own PNG into ARTIFACTS_DIR (embedded-figures folder, distinct from
    PAGES_DIR's full-page renders). Returns
    [{"file_path": str, "bbox": (x0,y0,x1,y1), "width": int, "height": int}, ...]
    ready to hand to database.create_image_artifact(artifact_kind="EMBEDDED_FIGURE").
    """
    candidates = extract_figures_from_page(image_path)
    saved = []
    for idx, candidate in enumerate(candidates, start=1):
        out_filename = f"{doc_slug}_p{page_num}_fig{idx}.png"
        out_path = ARTIFACTS_DIR / out_filename
        candidate["image"].save(out_path, format="PNG")
        saved.append(
            {
                "file_path": str(out_path),
                "bbox": candidate["bbox"],
                "width": candidate["image"].width,
                "height": candidate["image"].height,
            }
        )
    return saved
