"""
One active recording session globally: starting a new session ends all others.
"""

import json
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from models.audit_log import AuditLog
from models.plant import Plant
from models.session import RecordingSession


def close_all_open_sessions(db: Session) -> int:
    """Set ended_at = now on every session that is still open. Returns count closed."""
    now = datetime.utcnow()
    q = db.query(RecordingSession).filter(RecordingSession.ended_at.is_(None))
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
    if db.query(Plant).filter(Plant.id == plant_id).first() is None:
        raise ValueError("plant_not_found")
    close_all_open_sessions(db)
    s = RecordingSession(
        plant_id=plant_id,
        device_id=device_id,
        started_at=datetime.utcnow(),
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
    s.ended_at = datetime.utcnow()
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
    """Policy: at most one; list API still returns a list for compatibility."""
    return db.query(RecordingSession).filter(RecordingSession.ended_at.is_(None)).all()


def get_open_session_singleton(db: Session) -> Optional[RecordingSession]:
    """Single active sample: zero or one open session."""
    return db.query(RecordingSession).filter(RecordingSession.ended_at.is_(None)).first()


def list_sessions_for_plant(db: Session, plant_id: int) -> List[RecordingSession]:
    return (
        db.query(RecordingSession)
        .filter(RecordingSession.plant_id == plant_id)
        .order_by(RecordingSession.started_at.desc())
        .all()
    )
