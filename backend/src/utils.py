"""
utils.py
Shared helpers used across the extraction pipeline.
"""
import re
import threading
import time
from typing import Optional, Tuple

import httpx
import ollama

from src.config import OLLAMA_HOST

_NUMERIC_RE = re.compile(r"[-+]?\d[\d,]*\.?\d*")
# Matches a degrees-minutes-seconds coordinate (e.g. 19° 32' 45.12"), tried
# BEFORE _NUMERIC_RE below. Found as a real bug: _NUMERIC_RE grabs only the
# first number-shaped chunk of text and stops, so a DMS coordinate like
# 19° 32' 45.12" N was silently parsed as just 19.0 (dropping the minutes/
# seconds entirely) - a ~60km error - while still reporting ok=True, since
# 19.0 is a perfectly valid-looking float on its own. Character classes cover
# the common Unicode variants for the degree/minute/second marks (a VLM's
# transcription of a scanned symbol isn't guaranteed to be plain ASCII).
_DMS_RE = re.compile(
    r"(\d{1,3})\s*[°˚]\s*(\d{1,2}(?:\.\d+)?)\s*['’′]\s*"
    r"(\d{1,2}(?:\.\d+)?)\s*[\"”″]?"
)
_NEGATIVE_DIRECTIONS = {"S", "W"}

# Single global lock around every VLM call. This is a single-user local workstation
# tool with 4GB VRAM total and ~2.7GB already used by the loaded model - there is no
# headroom for two pages/documents to be processed concurrently, regardless of how
# many uploads a future router lets a user trigger at once. A plain threading.Lock
# (rather than asyncio.Semaphore) is deliberate: it serializes correctly whether the
# caller is a sync script, a FastAPI BackgroundTask, or an async route using
# run_in_threadpool - simple is fine here, this is not a multi-tenant service.
_VLM_LOCK = threading.Lock()


class OllamaUnavailableError(RuntimeError):
    """Ollama's server could not be reached at all - distinct from a model/prompt error."""


class OllamaConnectionError(OllamaUnavailableError):
    """
    Ollama's server process could not be reached at all (connection refused/
    timed out) - a stronger, more specific signal than the generic VRAM/
    done=False case (also an OllamaUnavailableError, but NOT this subclass).

    Confirmed directly against this machine's own Ollama install
    (AppData/Local/Ollama/upgrade.log): its Windows app silently downloads
    and installs updates in the background, force-closing the running
    server to do so and relaunching it once done - a full observed cycle
    took about 64 seconds. That's fundamentally different from the VRAM-
    pressure case: the server reliably comes back on its own here, so a
    caller should wait for it and resume the SAME page rather than burning
    one of that page's limited retry attempts (or worse, giving up and
    marking a page "failed" for a reason that had nothing to do with that
    page's actual content). See wait_for_ollama_recovery below.
    """


def wait_for_ollama_recovery(
    max_wait_seconds: float = 240.0, poll_interval_seconds: float = 5.0
) -> bool:
    """
    Blocks, polling Ollama with a cheap call (ollama.list(), no model load)
    every poll_interval_seconds, until it responds again or max_wait_seconds
    elapses.

    max_wait_seconds defaults comfortably above the ~64s real auto-update
    cycle observed directly on this machine, so a genuine update-driven
    outage rides itself out here - but this is NOT a fix for the separate
    VRAM-ceiling failure (a page that keeps failing with the server fully
    reachable): that was reproduced repeatedly even from a freshly-cleared
    GPU, so waiting longer for VRAM to "free up" doesn't help and isn't
    what this function is for. Callers must only invoke this for
    OllamaConnectionError, not the generic OllamaUnavailableError.

    Returns True once Ollama responds again, False if max_wait_seconds
    elapses without it coming back (a real, longer outage this function
    isn't meant to ride out - the caller should give up as normal).
    """
    waited = 0.0
    while waited < max_wait_seconds:
        try:
            ollama.list()
            return True
        except Exception:
            time.sleep(poll_interval_seconds)
            waited += poll_interval_seconds
    return False


def call_ollama_chat(
    *, model: str, prompt: str, image_path: Optional[str] = None, num_ctx: int, format: Optional[dict] = None
) -> dict:
    """
    Thin wrapper around ollama.chat() that classifies failure modes instead of
    letting a raw httpx traceback surface, and serializes all VLM calls behind
    one global lock (see _VLM_LOCK above).

    `image_path`: omit for a text-only call (e.g. rag_engine.py's grounded
    chat, which sends retrieved text context, not a page image) - Qwen2.5-VL
    is a VLM but text-only prompts work the same as any chat model.

    Ollama's own background auto-updater can silently kill the running server
    mid-session (observed directly during development - it launches OllamaSetup.exe
    unprompted and tears down the server process, see config.py). Without this
    wrapper that failure looks identical to a code bug (httpx.ConnectError deep in
    a stack trace) and costs real debugging time - and would be worse mid-demo,
    where "the model is misbehaving" and "Ollama isn't running" need very different
    responses. Every VLM call in this pipeline should go through here.

    `format`: an optional JSON Schema dict, passed straight through to Ollama's
    `format` parameter for grammar-constrained structured output. Pass this
    instead of relying solely on unified_parser.py's post-hoc regex repairs -
    verified directly that schema-constrained output eliminates JSON syntax
    malformations (fences, bare unquoted enums, trailing commas, garbage
    top-level keys) outright, which regex patches were only chasing one at a
    time after the fact. It does NOT fix semantic issues (e.g. a fabricated
    hazard entry that is syntactically valid) - see unified_parser.py's
    fabrication guard, which is still required regardless of this parameter.
    """
    try:
        message = {"role": "user", "content": prompt}
        if image_path is not None:
            message["images"] = [image_path]
        chat_kwargs = dict(
            model=model,
            messages=[message],
            options={
                "num_ctx": num_ctx,
                # Observed directly on a sparse/table-heavy page: generation degenerated
                # into hundreds of repeated tab characters and never produced valid JSON
                # (see unified_parser.py's _call_and_parse docstring). repeat_penalty above
                # Ollama's ~1.1 default suppressed the repetition loop in testing;
                # num_predict caps how long a runaway generation can run before being cut
                # off, bounding worst-case latency even if it degenerates again.
                "repeat_penalty": 1.2,
                "num_predict": 2048,
            },
        )
        if format is not None:
            chat_kwargs["format"] = format
        with _VLM_LOCK:
            response = ollama.chat(**chat_kwargs)
        if response.get("done") is False:
            # Observed directly: at excessive num_ctx on this 4GB card, generation
            # failed mid-stream and the client returned a partial response that looks
            # superficially normal (has "message"/"content") but is missing every
            # completion field (eval_count, done_reason, timings) a real response has.
            # No exception is raised by ollama-python for this - left alone it silently
            # becomes a JSON parse failure downstream with no indication why. Raising
            # here instead of letting it masquerade as a real (if malformed) response.
            raise OllamaUnavailableError(
                f"Ollama returned an incomplete response (done=False, no completion "
                f"metadata) for num_ctx={num_ctx} - this reproduced when VRAM usage was "
                f"pushed too close to this card's 4GB limit. Try a lower num_ctx, or "
                f"check `nvidia-smi` for available VRAM before retrying."
            )
        return response
    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
        raise OllamaConnectionError(
            f"Could not reach Ollama at {OLLAMA_HOST}. The server is not running or was "
            f"killed mid-session - check for OllamaSetup.exe in Task Manager (its "
            f"auto-updater does this without warning) and confirm `ollama list` responds "
            f"before retrying."
        ) from exc
    except ollama.ResponseError as exc:
        if "exceed_context_size_error" in str(exc) or "exceeds the available context" in str(exc):
            raise OllamaUnavailableError(
                f"num_ctx={num_ctx} was too small for this request. Increase "
                f"VLM_NUM_CTX_PASS1/VLM_NUM_CTX_PASS2 in config.py."
            ) from exc
        raise


def normalize_numeric(raw_value) -> Tuple[Optional[float], bool]:
    """
    Parses a numeric value out of raw VLM output text. Used for every numeric
    field the parser extracts (depth_m, total_depth_m, latitude, longitude,
    elevation) so unit/comma/direction handling stays in one place instead of
    being reimplemented per field.

    Strips thousands-separator commas and common unit suffixes (m, ft, psi),
    and converts a trailing compass direction letter (N/S/E/W) into a sign for
    coordinate values (S and W become negative).

    A degrees-minutes-seconds coordinate (e.g. "19° 32' 45.12\" N") is detected
    and converted to decimal degrees (degrees + minutes/60 + seconds/3600)
    before falling back to the plain single-number match below - see _DMS_RE's
    comment for why this exists (the plain regex alone silently truncated a
    DMS value to just its degrees component).

    Returns (parsed_float_or_None, ok). The VLM's stated confidence for a field
    is about legibility, not correctness (see unified_parser.py) - ok=False
    here is a second, independent signal and callers must downgrade that
    field's confidence to LOW and continue on failure, never crash the insert.
    """
    if raw_value is None:
        return None, False
    if isinstance(raw_value, bool):
        return None, False
    if isinstance(raw_value, (int, float)):
        return float(raw_value), True
    if not isinstance(raw_value, str):
        return None, False

    text = raw_value.strip()
    if not text:
        return None, False

    direction_sign = 1
    direction_match = re.search(r"\b([NSEW])\b", text.upper())
    if direction_match:
        if direction_match.group(1) in _NEGATIVE_DIRECTIONS:
            direction_sign = -1
        text = text[: direction_match.start()] + text[direction_match.end() :]

    dms_match = _DMS_RE.search(text)
    if dms_match:
        degrees, minutes, seconds = (float(g) for g in dms_match.groups())
        value = degrees + minutes / 60 + seconds / 3600
        return value * direction_sign, True

    match = _NUMERIC_RE.search(text)
    if not match:
        return None, False

    try:
        value = float(match.group(0).replace(",", ""))
    except ValueError:
        return None, False

    return value * direction_sign, True
