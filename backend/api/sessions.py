"""
Recording sessions — each user may have at most one open session; starting a new one
for that user closes their other open sessions.

Dummy streams are stopped only for sessions this user is replacing, not for other users.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session as OrmSession

from database import get_db
from deps.auth import get_current_user
from models.session import RecordingSession
from models.user import User
from schemas.session_schema import (
    ActiveSessionsResponse,
    RecordingSessionListResponse,
    RecordingSessionOut,
    RecordingSessionStart,
)
import services.recording_session_service as sess_svc
import services.plant_service as plant_svc
from services.dummy_stream import supervisor as stream_supervisor

router = APIRouter()


def _to_out(s) -> RecordingSessionOut:
    return RecordingSessionOut.model_validate(s)


@router.post("/start", response_model=RecordingSessionOut)
def start_session(
    body: RecordingSessionStart,
    db: OrmSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    open_mine = (
        db.query(RecordingSession)
        .filter(RecordingSession.ended_at.is_(None), RecordingSession.started_by == user.id)
        .all()
    )
    for o in open_mine:
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
            user_id=user.id,
            scenario=body.scenario,
            dummy_stream=body.dummy_stream,
            stream_interval_sec=body.stream_interval_sec,
        )
    except ValueError as e:
        err = str(e)
        if err == "plant_not_found":
            raise HTTPException(status_code=404, detail="Plant not found") from e
        if err == "plant_forbidden":
            raise HTTPException(status_code=403, detail="Not allowed for this sample") from e
        raise

    if body.dummy_stream:
        stream_supervisor.start(
            session_id=sess.id,
            plant_id=sess.plant_id,
            scenario=body.scenario or "stable",
            interval_sec=max(0.2, float(body.stream_interval_sec)),
        )
    return _to_out(sess)


@router.post("/{session_id}/stop", response_model=RecordingSessionOut)
def stop_session(
    session_id: int,
    db: OrmSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stream_supervisor.stop(session_id)

    s = sess_svc.stop_session(db, session_id, user_id=user.id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found or already ended")
    return _to_out(s)


@router.get("/active", response_model=ActiveSessionsResponse)
def active_sessions(db: OrmSession = Depends(get_db), user: User = Depends(get_current_user)):
    rows: List = sess_svc.get_active_sessions_for_user(db, user.id)
    return ActiveSessionsResponse(sessions=[_to_out(s) for s in rows])


@router.get("", response_model=RecordingSessionListResponse)
def list_sessions(
    plant_id: int = Query(...),
    db: OrmSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if plant_svc.get_plant_for_owner(db, plant_id, user.id) is None:
        raise HTTPException(status_code=404, detail="Plant not found")
    rows = sess_svc.list_sessions_for_plant(db, plant_id)
    return RecordingSessionListResponse(sessions=[_to_out(s) for s in rows])
