"""
One active recording session globally: starting a new session ends all others.
"""

import json
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from models.audit_log import AuditLog
from models.plant import Plant
from models.session import RecordingSession


def close_all_open_sessions(db: Session) -> int:
    """Set ended_at = now on every session that is still open. Returns count closed."""
    now = datetime.now(timezone.utc)
    q = db.query(RecordingSession).filter(RecordingSession.ended_at.is_(None))
    n = 0
    for row in q.all():
        row.ended_at = now
        n += 1
    if n:
        db.commit()
    return n


def close_open_sessions_for_user(db: Session, user_id: Optional[int]) -> int:
    """
    End open sessions owned by ``user_id``. When ``user_id`` is None (legacy callers),
    fall back to closing **all** open sessions (backward-compatible single-lab behavior).
    """
    now = ()
    q = db.query(RecordingSession).filter(RecordingSession.ended_at.is_(None))
    if user_id is not None:
        q = q.filter(RecordingSession.started_by == user_id)
    n = 0
    for row in q.all():
        row.ended_at = now
        n += 1
    if n:
        db.commit()
    return n


def start_session(
    db: Session,
    plant_id: int,
    device_id: Optional[int] = None,
    setpoint_temp: Optional[float] = None,
    setpoint_humidity: Optional[float] = None,
    setpoint_light: Optional[float] = None,
    notes: Optional[str] = None,
    user_id: Optional[int] = None,
    scenario: Optional[str] = None,
    dummy_stream: bool = False,
    stream_interval_sec: Optional[int] = None,
) -> RecordingSession:
    p = db.query(Plant).filter(Plant.id == plant_id).first()
    if p is None:
        raise ValueError("plant_not_found")
    if user_id is not None and p.owner_id is not None and p.owner_id != user_id:
        raise ValueError("plant_forbidden")
    close_open_sessions_for_user(db, user_id)
    s = RecordingSession(
        plant_id=plant_id,
        device_id=device_id,
        started_at=datetime.now(timezone.utc),
        ended_at=None,
        setpoint_temp=setpoint_temp,
        setpoint_humidity=setpoint_humidity,
        setpoint_light=setpoint_light,
        notes=notes,
        started_by=user_id,
        scenario=scenario,
        dummy_stream=bool(dummy_stream),
        stream_interval_sec=stream_interval_sec,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    db.add(
        AuditLog(
            entity_type="recording_session",
            entity_id=s.id,
            action="start",
            user_id=user_id,
            payload_json=json.dumps({
                "plant_id": plant_id,
                "device_id": device_id,
                "scenario": scenario,
                "dummy_stream": bool(dummy_stream),
                "stream_interval_sec": stream_interval_sec,
            }),
        )
    )
    db.commit()
    return s


def stop_session(db: Session, session_id: int, user_id: Optional[int] = None) -> Optional[RecordingSession]:
    s = db.query(RecordingSession).filter(RecordingSession.id == session_id).first()
    if not s or s.ended_at is not None:
        return None
    if user_id is not None:
        p = db.query(Plant).filter(Plant.id == s.plant_id).first()
        if p is not None and p.owner_id is not None and p.owner_id != user_id:
            return None
    s.ended_at = datetime.now(timezone.utc)
    db.add(
        AuditLog(
            entity_type="recording_session",
            entity_id=s.id,
            action="stop",
            user_id=user_id,
            payload_json=None,
        )
    )
    db.commit()
    db.refresh(s)
    return s


def get_active_sessions(db: Session) -> List[RecordingSession]:
    """All open sessions (may be several users, one per user typically)."""
    return db.query(RecordingSession).filter(RecordingSession.ended_at.is_(None)).all()


def get_active_sessions_for_user(db: Session, user_id: int) -> List[RecordingSession]:
    """Open sessions this user started (for UI active-recording indicator)."""
    return (
        db.query(RecordingSession)
        .filter(
            RecordingSession.started_by == user_id,
            RecordingSession.ended_at.is_(None),
        )
        .all()
    )


def get_open_session_singleton(db: Session) -> Optional[RecordingSession]:
    """One open session for backward-compat / Pi without plant_id (avoid if possible)."""
    return db.query(RecordingSession).filter(RecordingSession.ended_at.is_(None)).first()


def get_open_session_for_plant(db: Session, plant_id: int) -> Optional[RecordingSession]:
    """Open session for this plant, if any."""
    return (
        db.query(RecordingSession)
        .filter(RecordingSession.plant_id == plant_id, RecordingSession.ended_at.is_(None))
        .first()
    )


def get_any_open_session(db: Session) -> Optional[RecordingSession]:
    """Latest-started open session when ingest does not specify ``plant_id``."""
    return (
        db.query(RecordingSession)
        .filter(RecordingSession.ended_at.is_(None))
        .order_by(RecordingSession.started_at.desc())
        .first()
    )


def list_sessions_for_plant(db: Session, plant_id: int) -> List[RecordingSession]:
    return (
        db.query(RecordingSession)
        .filter(RecordingSession.plant_id == plant_id)
        .order_by(RecordingSession.started_at.desc())
        .all()
    )
