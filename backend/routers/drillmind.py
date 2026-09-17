"""
drillmind.py
POST /api/chat

document_ids: optional - DrillMind.jsx's "+" file picker lets a user scope a
question to specific documents from the corpus, instead of always searching
everything indexed. None (the default, and what every existing call already
sends) searches the whole corpus, unchanged.
"""
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from src import rag_engine

router = APIRouter(prefix="/api/chat", tags=["drillmind"])


class ChatRequest(BaseModel):
    message: str
    document_ids: Optional[list[int]] = None


@router.post("")
def chat(payload: ChatRequest):
    return rag_engine.ask(payload.message, document_ids=payload.document_ids)
