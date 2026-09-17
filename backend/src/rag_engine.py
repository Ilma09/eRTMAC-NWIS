"""
rag_engine.py
DrillMind's grounded answer generation: retrieves relevant page chunks via
vector_store.py, then asks Qwen2.5-VL (text-only - no image, see
utils.call_ollama_chat's image_path=None support) to answer strictly from that
retrieved context.

CORE PROJECT CONSTRAINT: DrillMind must never answer from the model's own
pretrained/general knowledge - only from documents actually indexed into
Qdrant. Two deterministic guards enforce this rather than trusting the prompt
alone (same "don't trust free-form LLM judgment for something that matters"
pattern as unified_parser.py's hazard whitelist):
  1. If retrieval returns zero chunks, the VLM is never called at all - a
     fixed "nothing found" response is returned directly.
  2. If the best retrieved chunk's similarity score is below RAG_MIN_SCORE,
     treat it the same as "nothing found" - a weakly-relevant chunk risks the
     model padding a thin match with outside knowledge rather than saying it
     doesn't know. RAG_MIN_SCORE is a starting point, not empirically
     calibrated against a labeled query set - revisit if real usage shows it's
     too strict (real answers wrongly suppressed) or too loose (weak matches
     still getting answered).

Citations are derived deterministically from what was actually retrieved and
fed to the model - never parsed from the model's own response text. A
self-reported citation is a new place for the model to be confidently wrong
(same lesson as trusting VLM-judged severity/status elsewhere in this
project); "here is what we gave it" is not something the model can get wrong.

Pure Python, no FastAPI awareness (routers not built yet).
"""
from typing import Optional

from src import database, vector_store
from src.config import RAG_TOP_K, VLM_MODEL_NAME, VLM_NUM_CTX_PASS1
from src.utils import OllamaUnavailableError, call_ollama_chat

# Cosine similarity floor - RAISED from an initial ungrounded guess of 0.35
# after real measurement against the actual indexed corpus: "What is the price
# of Brent crude oil today?" (genuinely irrelevant, but same-domain vocabulary)
# scored 0.48-0.52, well above 0.35 - it reached the VLM and got an empty
# answer instead of being caught by this guard. A true off-topic query
# ("chocolate cake") only scored 0.33-0.36; the genuinely relevant query
# scored 0.59-0.60. bge-small's cosine scores on short text don't spread out
# much, so 0.55 is chosen to separate the observed relevant-vs-domain-adjacent
# gap - still a small sample (3 queries, 2 indexed chunks), revisit with more
# real usage data rather than trusting this as final.
RAG_MIN_SCORE = 0.55

_NOT_FOUND_TEXT = (
    "I don't have any indexed documents that address this question. "
    "Nothing sufficiently relevant has been found in the corpus."
)

RAG_PROMPT_TEMPLATE = """You are DrillMind, an assistant for oil & gas drilling engineers. Answer the
question using ONLY the document excerpts below. Do not use any outside or
general knowledge, and do not fill in gaps with assumptions. If the excerpts
do not actually contain enough information to answer, say so explicitly in
your answer rather than guessing.

Document excerpts:
{context}

Question: {question}

Respond with ONLY a JSON object in this exact shape, no other text:
{{"text": "your answer, grounded strictly in the excerpts above"}}"""

RAG_SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
}


def _well_name_for(well_id: Optional[int], cache: dict) -> str:
    """vector_store.search() only carries well_id in its payload, not the name
    (it never had it - a real bug caught while testing, not a refactor). Looks
    it up via database.get_well(), matching the frontend's documented citation
    shape ({"well_name": ..., "page_num": ...}), with a per-call cache since
    the same well_id often repeats across a query's top-k chunks."""
    if well_id is None:
        return "Unknown"
    if well_id not in cache:
        well = database.get_well(well_id)
        cache[well_id] = well["well_name"] if well else "Unknown"
    return cache[well_id]


def ask(question: str, top_k: int = RAG_TOP_K, document_ids: Optional[list] = None) -> dict:
    """
    Returns {"text": str, "citations": [{well_name, document_id, page_num}]}.

    document_ids: optional - when given (DrillMind's "+" file picker),
    retrieval is restricted to only those documents' indexed pages, so the
    answer can only ever be grounded in the files the user actually picked.
    None (the default) searches the whole corpus, unchanged from before.

    citations is non-empty whenever chunks were retrieved and fed to the VLM,
    even if the VLM itself then failed to produce a usable answer (empty
    output is normalized to the same "not found" text as the score-gate
    below) - so citations reflect what was actually searched, not whether
    the answer is grounded. Frontend: don't infer "found vs not found" from
    citations.length alone; compare text against the literal "not found"
    message, or just label the list neutrally (e.g. "Pages searched") so it
    reads correctly in both cases.
    """
    chunks = vector_store.search(question, top_k=top_k, document_ids=document_ids)
    if not chunks or chunks[0]["score"] < RAG_MIN_SCORE:
        not_found_text = (
            "None of the file(s) you selected address this question."
            if document_ids
            else _NOT_FOUND_TEXT
        )
        return {"text": not_found_text, "citations": []}

    well_name_cache: dict = {}
    context = "\n\n".join(
        f"[Well: {_well_name_for(c['well_id'], well_name_cache)}, Page {c['page_num']}]\n{c['text']}"
        for c in chunks
    )
    prompt = RAG_PROMPT_TEMPLATE.format(context=context, question=question)

    try:
        response = call_ollama_chat(
            model=VLM_MODEL_NAME, prompt=prompt, num_ctx=VLM_NUM_CTX_PASS1, format=RAG_SCHEMA
        )
    except OllamaUnavailableError:
        return {
            "text": "The document assistant is temporarily unavailable. Please try again.",
            "citations": [],
        }

    answer_text = _extract_answer_text(response["message"]["content"])
    if not answer_text.strip():
        # Observed directly: a borderline-relevant query that passed RAG_MIN_SCORE
        # can still make the VLM return {"text": ""} - schema-constrained output
        # guarantees the key exists, not that it's non-empty or useful. An empty
        # response is a worse user experience than the same explicit "not found"
        # message the score-gate above already uses, so treat it identically -
        # citations still reflect what was actually retrieved and fed in, since
        # that part is real regardless of the VLM's empty answer.
        answer_text = _NOT_FOUND_TEXT

    citations = [
        {
            "well_name": _well_name_for(c["well_id"], well_name_cache),
            "document_id": c["document_id"],
            "page_num": c["page_num"],
        }
        for c in chunks
    ]
    return {"text": answer_text, "citations": citations}


def _extract_answer_text(raw_text: str) -> str:
    """Schema-constrained output (see module docstring) means this should
    always be clean {"text": "..."} JSON - but falls back to the raw text
    itself rather than a hard failure if that ever isn't true, since a chat
    answer degrading to "raw text, unquoted" is a far better user experience
    than an error page for a feature people are actively typing into live."""
    import json

    try:
        parsed = json.loads(raw_text.strip())
        if isinstance(parsed, dict) and isinstance(parsed.get("text"), str):
            return parsed["text"]
    except json.JSONDecodeError:
        pass
    return raw_text.strip()
