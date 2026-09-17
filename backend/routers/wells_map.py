"""
wells_map.py
GET /api/wells, POST /api/wells

Per explicit decision: returns the project's actual oil/gas well data shape
(matching what unified_parser.py extracts), NOT MapVisualise.jsx's current
mock shape. That mock (type: "Active"/"Historical", status: "Monitoring"/
"Archived", a waterLevel field) models GROUNDWATER monitoring wells - a
different domain from this project's oil & gas WCR/hazard pipeline, and looks
like unrelated placeholder content rather than a real target to preserve.
waterLevel has no backing data in this domain and is intentionally omitted
rather than faked.

POST lets a user manually pin a well straight onto the map (MapVisualise.jsx's
"Add Well" form) rather than only ever getting wells from document extraction.
location_verified is always True for these - a human placed the pin directly,
which is a stronger signal than anything the extraction pipeline infers from
document text.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src import database

router = APIRouter(prefix="/api/wells", tags=["wells"])


def _serialize_well(well: dict) -> dict:
    return {
        "id": well["well_id"],
        "name": well["well_name"],
        "type": well.get("well_type") or "Unknown",
        "lat": well["latitude"],
        "lng": well["longitude"],
        "location_verified": bool(well.get("location_verified")),
        "depth": well.get("total_depth_m"),
        "date": well.get("created_at"),
        "status": well.get("status"),
        "location": well.get("field_location") or "Unknown",
        "operator": well.get("operator"),
        # All derived from already-transcribed text via regex, not the VLM -
        # see unified_parser.derive_well_enrichment. Any of these can be
        # None; not every document states these in a form the heuristic
        # catches (see that function's docstring - it's deliberately simple,
        # not exhaustive).
        "formation": well.get("formation"),
        "mud_type": well.get("mud_type"),
        "mud_weight": well.get("mud_weight"),
        "casing_notes": well.get("casing_notes"),
        "cementing_notes": well.get("cementing_notes"),
        "reservoir_notes": well.get("reservoir_notes"),
    }


def _serialize_hazard(hazard: dict) -> dict:
    return {
        "hazard_type": hazard.get("hazard_type"),
        "depth_m": hazard.get("depth_m"),
        "severity": hazard.get("severity"),
        "confidence": hazard.get("confidence"),
        "page_num": hazard.get("page_num"),
        "description": hazard.get("description"),
    }


class NewWellRequest(BaseModel):
    name: str
    latitude: float
    longitude: float
    well_type: Optional[str] = None
    status: str = "ACTIVE"


class CompareWellsRequest(BaseModel):
    well_ids: list[int]


@router.get("")
def list_wells():
    return [_serialize_well(well) for well in database.list_wells()]


@router.post("")
def add_well(payload: NewWellRequest):
    well_id = database.create_well(
        well_name=payload.name,
        operator=None,
        latitude=payload.latitude,
        longitude=payload.longitude,
        total_depth_m=None,
        status=payload.status,
        location_verified=True,
        well_type=payload.well_type,
        field_location=None,
    )
    return _serialize_well(database.get_well(well_id))


@router.post("/compare")
def compare_wells(payload: CompareWellsRequest):
    """
    Powers the Risk Monitor's Well Comparison sub-section: given a list of
    well ids picked directly from the corpus (no coordinates required, unlike
    the radius-based Hazard Proximity Check), returns each well's real data
    plus its full hazard list, flags any hazard_type shared by 2+ of the
    selected wells, and separately flags hazard_type/formation pairs shared
    by 2+ wells that also report the SAME formation - the PS's "formation-
    specific risks across wells" correlation, one level more specific than
    the plain hazard-type overlap above. Both are the simplest honest signal
    this data supports without inventing a scoring model; well_count in each
    counts distinct wells, not raw hazard rows (a well with 3 "kick" entries
    still only counts once).
    """
    if not payload.well_ids:
        raise HTTPException(status_code=400, detail="well_ids must not be empty")

    wells = []
    hazard_type_wells: dict = {}
    formation_hazard_wells: dict = {}

    for well_id in payload.well_ids:
        well = database.get_well(well_id)
        if well is None:
            continue
        hazards = [_serialize_hazard(h) for h in database.get_hazards_for_well(well_id)]
        formation = (well.get("formation") or "").strip()
        seen_types_this_well = set()
        for hazard in hazards:
            key = (hazard["hazard_type"] or "Unknown").strip().lower()
            seen_types_this_well.add(key)
        for key in seen_types_this_well:
            hazard_type_wells.setdefault(key, set()).add(well_id)
            if formation:
                formation_key = (formation.lower(), key)
                formation_hazard_wells.setdefault(formation_key, set()).add(well_id)
        wells.append({**_serialize_well(well), "hazards": hazards})

    shared_hazard_types = sorted(
        [
            {"hazard_type": key, "well_count": len(well_ids)}
            for key, well_ids in hazard_type_wells.items()
            if len(well_ids) >= 2
        ],
        key=lambda x: -x["well_count"],
    )

    formation_hazard_correlation = sorted(
        [
            {"formation": formation, "hazard_type": hazard_type, "well_count": len(well_ids)}
            for (formation, hazard_type), well_ids in formation_hazard_wells.items()
            if len(well_ids) >= 2
        ],
        key=lambda x: -x["well_count"],
    )

    return {
        "wells": wells,
        "shared_hazard_types": shared_hazard_types,
        "formation_hazard_correlation": formation_hazard_correlation,
    }
