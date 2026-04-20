"""
Recording sessions — one active sample globally: starting a session closes any other.

Side effects layered on top of the pure service:
* When ``dummy_stream=true`` is requested, the streaming supervisor is asked to
  start (or stop on session stop). This keeps service-layer code DB-only
  testable while concentrating asyncio/process-state concerns at the API edge.
* Pre-empting an existing session also stops its dummy stream, so two samples
  never get cross-contaminated readings.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session as OrmSession

from database import get_db
from models.session import RecordingSession
from schemas.session_schema import (
    ActiveSessionsResponse,
    RecordingSessionListResponse,
    RecordingSessionOut,
    RecordingSessionStart,
)
import services.recording_session_service as sess_svc
from services.dummy_stream import supervisor as stream_supervisor

router = APIRouter()


def _to_out(s) -> RecordingSessionOut:
    return RecordingSessionOut.model_validate(s)


@router.post("/start", response_model=RecordingSessionOut)
def start_session(body: RecordingSessionStart, db: OrmSession = Depends(get_db)):
    # Find any session that's about to be pre-empted so we can also stop its
    # streaming task. The service layer would otherwise just close the row.
    open_others = db.query(RecordingSession).filter(RecordingSession.ended_at.is_(None)).all()
    for o in open_others:
        stream_supervisor.stop(o.id)

    try:
        sess = sess_svc.start_session(
            db,
            plant_id=body.plant_id,
            device_id=body.device_id,
            setpoint_temp=body.setpoint_temp,
            setpoint_humidity=body.setpoint_humidity,
            setpoint_light=body.setpoint_light,
            notes=body.notes,
            scenario=body.scenario,
            dummy_stream=body.dummy_stream,
            stream_interval_sec=body.stream_interval_sec,
        )
    except ValueError as e:
        if str(e) == "plant_not_found":
            raise HTTPException(status_code=404, detail="Plant not found") from e
        raise

    if body.dummy_stream:
        stream_supervisor.start(
            session_id=sess.id,
            plant_id=sess.plant_id,
            scenario=body.scenario or "stable",
            interval_sec=body.stream_interval_sec or 5,
        )
    return _to_out(sess)


@router.post("/{session_id}/stop", response_model=RecordingSessionOut)
def stop_session(session_id: int, db: OrmSession = Depends(get_db)):
    # Always stop the streaming task first, even if the row is already closed
    # — the supervisor.stop() is a no-op when nothing is running.
    stream_supervisor.stop(session_id)

    s = sess_svc.stop_session(db, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found or already ended")
    return _to_out(s)


@router.get("/active", response_model=ActiveSessionsResponse)
def active_sessions(db: OrmSession = Depends(get_db)):
    rows: List = sess_svc.get_active_sessions(db)
    return ActiveSessionsResponse(sessions=[_to_out(s) for s in rows])


@router.get("", response_model=RecordingSessionListResponse)
def list_sessions(plant_id: Optional[int] = Query(None), db: OrmSession = Depends(get_db)):
    if plant_id is None:
        raise HTTPException(status_code=400, detail="plant_id query parameter is required")
    rows = sess_svc.list_sessions_for_plant(db, plant_id)
    return RecordingSessionListResponse(sessions=[_to_out(s) for s in rows])
