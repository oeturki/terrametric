"""
FR1 / FR2 - Environmental Monitoring & Data Logging endpoints.
Ingest is open (Arduino / Pi); reads require auth and are scoped to the user's plants.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from deps.auth import get_current_user
from models.plant import Plant
from models.user import User
from schemas.ingest import TelemetryIngest, TelemetryIngestResult
from services.telemetry_service import (
    get_latest_reading_for_plant_ids,
    get_per_plant_timeseries_data,
    get_telemetry_timeseries_data,
    store_telemetry_row,
)

router = APIRouter()


def _ingest_result_message(session_id: Optional[int], link_hint: Optional[str]) -> Optional[str]:
    if session_id is not None:
        return None
    if link_hint == "open_sessions_on_other_plants":
        return "no_session_for_this_plant_recording_on_other_sample"
    return "no_active_recording_session"


def _owner_plant_ids(db: Session, user_id: int) -> List[int]:
    return [r[0] for r in db.query(Plant.id).filter(Plant.owner_id == user_id).all()]


def _parse_int_csv(raw: Optional[str]) -> List[int]:
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


def _require_owned_subset(db: Session, user: User, pids: List[int]) -> None:
    if not pids:
        return
    owned = set(_owner_plant_ids(db, user.id))
    if not set(pids).issubset(owned):
        raise HTTPException(status_code=403, detail="One or more sample ids are not yours")


@router.get("/latest")
def get_latest(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ids = _owner_plant_ids(db, user.id)
    row = get_latest_reading_for_plant_ids(db, ids)
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
    plant_id: int | None = Query(None, description="Restrict to telemetry for this plant"),
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
        None,
        ge=0,
        le=86400,
        description="If > 0, mean-bucket readings into fixed time windows for downsampling.",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    mine = _owner_plant_ids(db, user.id)
    ids = _parse_int_csv(plant_ids)
    if ids:
        _require_owned_subset(db, user, ids)
        return get_telemetry_timeseries_data(
            db,
            hours,
            plant_id=None,
            plant_ids=ids,
            bin_seconds=bin_seconds,
            session_id=session_id,
        )
    if plant_id is not None:
        _require_owned_subset(db, user, [plant_id])
        return get_telemetry_timeseries_data(
            db,
            hours,
            plant_id=plant_id,
            plant_ids=None,
            bin_seconds=bin_seconds,
            session_id=session_id,
        )
    if not mine:
        return {
            "timestamps": [],
            "temperature": [],
            "humidity": [],
            "light": [],
            "plant_height": [],
            "bin_seconds": bin_seconds or 0,
            "row_count": 0,
        }
    return get_telemetry_timeseries_data(
        db,
        hours,
        plant_id=None,
        plant_ids=mine,
        bin_seconds=bin_seconds,
        session_id=session_id,
    )


@router.get("/timeseries/by-plant")
def get_telemetry_timeseries_by_plant(
    plant_ids: str = Query(..., description="Comma-separated plant IDs (required)."),
    hours: int = Query(24, ge=1, le=8760),
    bin_seconds: Optional[int] = Query(None, ge=0, le=86400),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ids = _parse_int_csv(plant_ids)
    if not ids:
        return get_per_plant_timeseries_data(db, [], hours=hours, bin_seconds=bin_seconds)
    _require_owned_subset(db, user, ids)
    return get_per_plant_timeseries_data(db, ids, hours=hours, bin_seconds=bin_seconds)


@router.post("/ingest", response_model=TelemetryIngestResult)
def ingest_telemetry(body: TelemetryIngest, db: Session = Depends(get_db)):
    row, link_hint = store_telemetry_row(
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
        plant_id=body.plant_id,
    )
    return TelemetryIngestResult(
        stored=True,
        session_id=row.session_id,
        message=_ingest_result_message(row.session_id, link_hint),
    )
