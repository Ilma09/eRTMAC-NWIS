"""
vector_store.py
Semantic search over extracted page text: embeds page text with bge-small-en-v1.5
and indexes it into an embedded (local, on-disk, no server) Qdrant collection for
RAG retrieval (DrillMind).

Deliberately separate from unified_parser.py (see that module's docstring: "Out
of scope for this module... embedding page text and indexing into Qdrant is
vector_store.py's job") - this module only embeds/indexes/searches. It has no
VLM/Ollama awareness and no HTTP/FastAPI awareness (routers not built yet).

One page = one chunk, matching the documented architecture exactly (page-level
citations, not sub-page offsets) - not introducing finer-grained chunking beyond
what was specified.

HARDWARE CONSTRAINT: the embedding model MUST run on CPU, forced explicitly via
device="cpu" below. The VLM already runs this 4GB card close to its limit (see
config.py's VLM_NUM_CTX_PASS2 note - the model spills partially onto CPU even by
itself); embedding on GPU would compete for the same scarce VRAM instead of
running in the ~300MB of system RAM it's supposed to use per the original spec.
"""
import uuid
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, FieldCondition, Filter, MatchAny, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer

from src.config import EMBEDDING_DIM, EMBEDDING_MODEL_NAME, QDRANT_COLLECTION_NAME, QDRANT_PATH, RAG_TOP_K

# bge-small-en-v1.5's own model card specifies this instruction prefix on the
# QUERY side ONLY for retrieval (asymmetric search) - passages/documents are
# embedded plain, without it. Getting this backwards measurably hurts retrieval
# quality; it is not optional decoration.
_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "

_model: Optional[SentenceTransformer] = None
_client: Optional[QdrantClient] = None


def _get_model() -> SentenceTransformer:
    """Lazily loads bge-small-en-v1.5, forced onto CPU (see module docstring)."""
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME, device="cpu")
    return _model


def _ensure_collection(client: QdrantClient):
    existing = {c.name for c in client.get_collections().collections}
    if QDRANT_COLLECTION_NAME not in existing:
        client.create_collection(
            collection_name=QDRANT_COLLECTION_NAME,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )


def _get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(path=str(QDRANT_PATH))
        _ensure_collection(_client)
    return _client


def _point_id(document_id: int, page_num: int) -> str:
    """Deterministic UUID from (document_id, page_num) so re-indexing the same
    page overwrites rather than duplicates - Qdrant's upsert is insert-or-replace
    keyed by point ID, not append-only."""
    return str(uuid.uuid5(uuid.NAMESPACE_OID, f"{document_id}:{page_num}"))


def index_page(*, well_id: Optional[int], document_id: int, page_num: int, page_text: str) -> bool:
    """Embeds one page's transcribed text (unified_parser.py's Pass 2 output,
    extract_page_content()'s "page_text") and upserts it into Qdrant.

    Skips genuinely empty text - nothing useful to search on, and it includes
    the case of a page whose Pass 2 call failed to parse (see unified_parser.py's
    accepted-limitation note: parse_ok=False pages return page_text=""). Returns
    False when skipped, True when indexed, so a caller can track how many of a
    document's pages actually made it into the index vs silently losing count."""
    if not page_text or not page_text.strip():
        return False
    model = _get_model()
    vector = model.encode(page_text, normalize_embeddings=True).tolist()
    client = _get_client()
    client.upsert(
        collection_name=QDRANT_COLLECTION_NAME,
        points=[
            PointStruct(
                id=_point_id(document_id, page_num),
                vector=vector,
                payload={
                    "well_id": well_id,
                    "document_id": document_id,
                    "page_num": page_num,
                    "text": page_text,
                },
            )
        ],
    )
    return True


def search(query: str, top_k: int = RAG_TOP_K, document_ids: Optional[list] = None) -> list:
    """Returns up to top_k {well_id, document_id, page_num, text, score} matches
    for the query, ranked by cosine similarity (highest first).

    document_ids: when given, restricts the search to only chunks from those
    documents (DrillMind's "+" file picker) - every indexed chunk already
    carries its document_id in the payload (see index_page), so this is a
    native Qdrant payload filter, not a post-hoc Python filter over the full
    collection.

    Used by rag_engine.py to retrieve grounded context for DrillMind - this
    module does retrieval only, no answer generation. Per the project's core
    constraint, DrillMind must never answer from an empty result here as if
    it were general knowledge - an empty list means nothing relevant is
    indexed (or nothing relevant in the selected files), and the caller must
    say so rather than fall back to the VLM's own pretrained knowledge."""
    model = _get_model()
    query_vector = model.encode(_QUERY_INSTRUCTION + query, normalize_embeddings=True).tolist()
    client = _get_client()
    query_filter = None
    if document_ids:
        query_filter = Filter(
            must=[FieldCondition(key="document_id", match=MatchAny(any=document_ids))]
        )
    results = client.query_points(
        collection_name=QDRANT_COLLECTION_NAME,
        query=query_vector,
        query_filter=query_filter,
        limit=top_k,
    ).points
    return [
        {
            "well_id": r.payload.get("well_id"),
            "document_id": r.payload.get("document_id"),
            "page_num": r.payload.get("page_num"),
            "text": r.payload.get("text"),
            "score": r.score,
        }
        for r in results
    ]


def count_indexed_chunks() -> int:
    client = _get_client()
    return client.count(collection_name=QDRANT_COLLECTION_NAME).count
