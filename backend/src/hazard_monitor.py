"""
hazard_monitor.py
Real-time spatial-vertical hazard correlation engine, per the architecture spec
(Layer 3): given a live rig position (lat, lon) and current bit depth, flags
historical NPT hazards from nearby offset wells.

Two-stage check, both must be true for an alert:
  1. Surface geodesic distance from the rig to the well <= SEARCH_RADIUS_KM (10.0 km)
  2. |hazard_depth - bit_depth| <= DEPTH_WINDOW_M (50m)

Pure Python, no FastAPI/HTTP awareness (routers not built yet) - matches the
project's src/ module convention.

Respects unified_parser.py's confidence design rather than re-deciding it here:
  - A well with missing or unverified coordinates (location_verified=0) never
    participates in the radius check - enforced by filtering on that flag
    before any distance is even computed, not by trusting an unverified
    lat/lon pair. The reading is still stored in `wells`; it just cannot
    trigger a live alert until a human reviews and verifies it.
  - A hazard with LOW confidence never participates in the depth-window check
    - enforced in database.find_hazards_in_depth_window's SQL (confidence IN
    ('HIGH', 'MEDIUM')), not duplicated here. See that function's docstring.
Both exclusions mean "no alert" is not the same as "definitely no hazard
nearby" - it may mean "the evidence exists but isn't trusted enough yet",
which is the entire point of NEEDS_REVIEW existing elsewhere in the pipeline.
"""
from typing import Optional

from geopy.distance import geodesic

from src import database
from src.config import DEPTH_WINDOW_M, SEARCH_RADIUS_KM


def find_nearby_wells(latitude: float, longitude: float, radius_km: float = SEARCH_RADIUS_KM) -> list:
    """Returns wells within radius_km of (latitude, longitude), each with an
    added "distance_km" field. Excludes any well without verified coordinates
    (location_verified=0, or a null lat/lon) - see module docstring."""
    nearby = []
    for well in database.list_wells():
        if not well.get("location_verified"):
            continue
        if well.get("latitude") is None or well.get("longitude") is None:
            continue
        distance_km = geodesic((latitude, longitude), (well["latitude"], well["longitude"])).km
        if distance_km <= radius_km:
            nearby.append({**well, "distance_km": distance_km})
    return nearby


def check_hazard_proximity(
    latitude: float,
    longitude: float,
    bit_depth_m: float,
    radius_km: float = SEARCH_RADIUS_KM,
    depth_window_m: float = DEPTH_WINDOW_M,
) -> dict:
    """
    The main entry point: given current rig telemetry, returns
    {"triggered": bool, "alerts": [...]}.

    Each alert: {well_name, hazard_type, hazard_depth_m, distance_km, severity,
    confidence}. Field names match the frontend's documented RiskMonitor.jsx
    response shape (well_name, hazard_type, hazard_depth_m, distance_km,
    severity) with confidence added as extra context, not a replacement for
    the frontend's expected fields.
    """
    nearby_wells = find_nearby_wells(latitude, longitude, radius_km)
    if not nearby_wells:
        return {"triggered": False, "alerts": []}

    distance_by_well_id = {well["well_id"]: well["distance_km"] for well in nearby_wells}
    well_ids = list(distance_by_well_id.keys())

    hazards = database.find_hazards_in_depth_window(well_ids, bit_depth_m, depth_window_m)

    alerts = [
        {
            "well_name": hazard["well_name"],
            "hazard_type": hazard["hazard_type"],
            "hazard_depth_m": hazard["depth_m"],
            "distance_km": round(distance_by_well_id[hazard["well_id"]], 2),
            "severity": hazard["severity"],
            "confidence": hazard["confidence"],
        }
        for hazard in hazards
    ]

    return {"triggered": bool(alerts), "alerts": alerts}
