"""
FR1 / FR2 - Environmental Monitoring & Data Logging endpoints.
Ingest sensor readings, query time-series data.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from schemas.ingest import TelemetryIngest, TelemetryIngestResult
from services.telemetry_service import (
    get_latest_reading,
    get_per_plant_timeseries_data,
    get_telemetry_timeseries_data,
    store_telemetry_row,
)

router = APIRouter()


def _parse_int_csv(raw: Optional[str]) -> List[int]:
    """Accept '1,2,3' or '1' or empty/None -> List[int]. Silently drops malformed."""
    if not raw:
        return []
    out: List[int] = []
    for piece in str(raw).split(","):
        piece = piece.strip()
        if not piece:
            continue
        try:
            out.append(int(piece))
        except ValueError:
            continue
    return out


@router.get("/latest")
def get_latest(db: Session = Depends(get_db)):
    row = get_latest_reading(db)
    if not row:
        return {
            "temperature": None,
            "humidity": None,
            "light": None,
            "height": None,
            "motion": None,
            "timestamp": None,
        }
    return row


@router.get("/timeseries")
def get_telemetry_timeseries(
    hours: int = Query(24, ge=1, le=8760, description="Time range in hours for historical data"),
    plant_id: int | None = Query(None, description="Restrict to telemetry from sessions for this plant"),
    plant_ids: Optional[str] = Query(
        None,
        description="Comma-separated list of plant IDs to include (combined into one series). "
                    "Takes precedence over plant_id.",
    ),
    session_id: int | None = Query(
        None,
        description="If set, only rows tagged to this recording session (excludes backfill with null session).",
    ),
    bin_seconds: Optional[int] = Query(
        None, ge=0, le=86400,
        description="If > 0, mean-bucket readings into fixed time windows for downsampling.",
    ),
    db: Session = Depends(get_db),
):
    ids = _parse_int_csv(plant_ids)
    return get_telemetry_timeseries_data(
        db, hours, plant_id=plant_id, plant_ids=ids if ids else None,
        bin_seconds=bin_seconds,
        session_id=session_id,
    )


@router.get("/timeseries/by-plant")
def get_telemetry_timeseries_by_plant(
    plant_ids: str = Query(..., description="Comma-separated plant IDs (required)."),
    hours: int = Query(24, ge=1, le=8760),
    bin_seconds: Optional[int] = Query(None, ge=0, le=86400),
    db: Session = Depends(get_db),
):
    """
    Compare-mode endpoint. Returns one series per plant_id so the frontend can
    overlay them with distinct colours. The single-series /timeseries endpoint
    is left untouched for legacy callers.
    """
    ids = _parse_int_csv(plant_ids)
    return get_per_plant_timeseries_data(db, ids, hours=hours, bin_seconds=bin_seconds)


@router.post("/ingest", response_model=TelemetryIngestResult)
def ingest_telemetry(body: TelemetryIngest, db: Session = Depends(get_db)):
    row = store_telemetry_row(
        db,
        temperature=body.temperature,
        humidity=body.humidity,
        movement=body.movement,
        light=body.light,
        distance=body.distance,
        plant_height=body.plant_height,
        timestamp=body.timestamp,
        device_id=body.device_id,
        bt_name=body.bt_name,
    )
    return TelemetryIngestResult(
        stored=True,
        session_id=row.session_id,
        message=None if row.session_id else "no_active_recording_session",
    )
