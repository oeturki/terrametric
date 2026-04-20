"""
FR7 — CRUD for plants (samples / trays).
"""

import json
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from models.audit_log import AuditLog
from models.plant import Plant
from schemas.plant import PlantCreate, PlantUpdate


def list_plants(db: Session) -> List[Plant]:
    return db.query(Plant).order_by(Plant.id).all()


def get_plant(db: Session, plant_id: int) -> Optional[Plant]:
    return db.query(Plant).filter(Plant.id == plant_id).first()


def get_plant_by_qr(db: Session, qr: str) -> Optional[Plant]:
    return db.query(Plant).filter(Plant.qr_code == qr).first()


def create_plant(db: Session, data: PlantCreate, user_id: Optional[int] = None) -> Plant:
    p = Plant(
        name=data.name,
        location=data.location,
        germination_date=data.germination_date,
        notes=data.notes,
        qr_code=data.qr_code,
        species=data.species,
        genotype=data.genotype,
        treatment_group=data.treatment_group,
        parent_plant_id=data.parent_plant_id,
        generation=data.generation,
        lifecycle_state=data.lifecycle_state or "registered",
        created_by=user_id,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    db.add(
        AuditLog(
            entity_type="plant",
            entity_id=p.id,
            action="create",
            user_id=user_id,
            payload_json=json.dumps({"qr_code": p.qr_code, "name": p.name}),
        )
    )
    db.commit()
    return p


def update_plant(db: Session, plant_id: int, data: PlantUpdate, user_id: Optional[int] = None) -> Optional[Plant]:
    p = get_plant(db, plant_id)
    if not p:
        return None
    payload = data.model_dump(exclude_unset=True, by_alias=True)
    alias_to_attr = {"loc": "location", "germ": "germination_date", "qr": "qr_code"}
    for k, v in payload.items():
        attr = alias_to_attr.get(k, k)
        if hasattr(p, attr):
            setattr(p, attr, v)
    p.updated_at = datetime.utcnow()
    db.add(
        AuditLog(
            entity_type="plant",
            entity_id=p.id,
            action="update",
            user_id=user_id,
            payload_json=json.dumps({k: str(v) for k, v in payload.items()}),
        )
    )
    db.commit()
    db.refresh(p)
    return p


def delete_plant(db: Session, plant_id: int, user_id: Optional[int] = None) -> bool:
    from models.reading import Telemetry
    from models.session import RecordingSession

    p = get_plant(db, plant_id)
    if not p:
        return False
    sess_ids = [r.id for r in db.query(RecordingSession).filter(RecordingSession.plant_id == plant_id).all()]
    # Telemetry can be linked via plant_id directly OR via session_id (older rows). Cover both.
    db.query(Telemetry).filter(Telemetry.plant_id == plant_id).delete(synchronize_session=False)
    if sess_ids:
        db.query(Telemetry).filter(Telemetry.session_id.in_(sess_ids)).delete(synchronize_session=False)
        db.query(RecordingSession).filter(RecordingSession.plant_id == plant_id).delete(synchronize_session=False)
    db.add(
        AuditLog(
            entity_type="plant",
            entity_id=plant_id,
            action="delete",
            user_id=user_id,
            payload_json=None,
        )
    )
    db.delete(p)
    db.commit()
    return True


def clear_telemetry_for_plant(db: Session, plant_id: int, user_id: Optional[int] = None) -> Optional[int]:
    """
    Wipe all telemetry rows tagged for a plant WITHOUT deleting the plant itself.
    Closes any open recording session for that plant first so the next reading
    doesn't immediately repopulate it.
    Returns the number of telemetry rows removed, or None if the plant doesn't exist.
    """
    from models.reading import Telemetry
    from models.session import RecordingSession

    p = get_plant(db, plant_id)
    if not p:
        return None

    # Stop any open session for this plant (do NOT touch other plants' sessions).
    open_sessions = (
        db.query(RecordingSession)
        .filter(RecordingSession.plant_id == plant_id, RecordingSession.ended_at.is_(None))
        .all()
    )
    now = datetime.utcnow()
    for s in open_sessions:
        s.ended_at = now

    sess_ids = [r.id for r in db.query(RecordingSession).filter(RecordingSession.plant_id == plant_id).all()]
    deleted_by_plant = (
        db.query(Telemetry)
        .filter(Telemetry.plant_id == plant_id)
        .delete(synchronize_session=False)
    )
    deleted_by_session = 0
    if sess_ids:
        deleted_by_session = (
            db.query(Telemetry)
            .filter(Telemetry.session_id.in_(sess_ids), Telemetry.plant_id.is_(None))
            .delete(synchronize_session=False)
        )
    total = int(deleted_by_plant) + int(deleted_by_session)
    db.add(
        AuditLog(
            entity_type="plant",
            entity_id=plant_id,
            action="clear_telemetry",
            user_id=user_id,
            payload_json=json.dumps({"rows_deleted": total, "sessions_closed": len(open_sessions)}),
        )
    )
    db.commit()
    return total


def delete_all_plants(db: Session, user_id: Optional[int] = None) -> int:
    """Cascading delete every plant. Returns the number of plants removed."""
    ids = [p.id for p in db.query(Plant).all()]
    removed = 0
    for pid in ids:
        if delete_plant(db, pid, user_id=user_id):
            removed += 1
    db.add(
        AuditLog(
            entity_type="plant",
            entity_id=None,
            action="delete_all",
            user_id=user_id,
            payload_json=json.dumps({"removed": removed}),
        )
    )
    db.commit()
    return removed
