"""
risk.py
POST /api/risk/telemetry

Per explicit decision: built per the original architecture spec, matching
hazard_monitor.py's already-built and validated check_hazard_proximity()
exactly - {lat, lng, bit_depth_m} in, {triggered, alerts} out. RiskMonitor.jsx
currently has no telemetry input UI at all (no lat/lng/depth fields, no
submit button - it's a static regional risk dashboard), so wiring this up
will need a new form added to that page, not just a fetch-swap. That's
expected frontend work, separate from this endpoint being correct.
"""
from fastapi import APIRouter
from pydantic import BaseModel

from src import hazard_monitor

router = APIRouter(prefix="/api/risk", tags=["risk"])


class TelemetryRequest(BaseModel):
    lat: float
    lng: float
    bit_depth_m: float


@router.post("/telemetry")
def check_telemetry(payload: TelemetryRequest):
    return hazard_monitor.check_hazard_proximity(
        latitude=payload.lat, longitude=payload.lng, bit_depth_m=payload.bit_depth_m
    )
