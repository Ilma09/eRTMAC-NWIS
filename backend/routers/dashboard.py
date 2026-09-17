"""
dashboard.py
GET /api/dashboard/summary

Dashboard.jsx has no mock data object to match - every number on that page is
hardcoded directly as literal JSX text ("1,248" etc.), not bound to a named
field. There is nothing to "match exactly" here; this follows the simple
4-field shape from the frontend description doc instead.
"""
from fastapi import APIRouter

from src import database

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary")
def get_summary():
    return {
        "total_wells": database.count_wells(),
        "active_wells": database.count_wells(active_only=True),
        "total_documents": database.count_documents(),
        "total_hazards": database.count_hazards(),
    }
