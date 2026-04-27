"""
FR7 — CRUD for plants (samples / trays).
"""

import json
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from models.audit_log import AuditLog
from models.plant import Plant
from models.plant_control import PlantControl
from schemas.plant import PlantCreate, PlantUpdate
from services.default_control_profile import default_control_json


def list_plants(db: Session, owner_id: Optional[int] = None) -> List[Plant]:
    q = db.query(Plant)
    if owner_id is not None:
        q = q.filter(Plant.owner_id == owner_id)
    return q.order_by(Plant.id).all()


def get_plant(db: Session, plant_id: int) -> Optional[Plant]:
    return db.query(Plant).filter(Plant.id == plant_id).first()


def get_plant_for_owner(db: Session, plant_id: int, owner_id: int) -> Optional[Plant]:
    return (
        db.query(Plant)
        .filter(Plant.id == plant_id, Plant.owner_id == owner_id)
        .first()
    )


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
        owner_id=user_id,
    )
    db.add(p)
    db.flush()
    db.add(PlantControl(plant_id=p.id, profile_json=default_control_json()))
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
    if user_id is not None and p.owner_id is not None and p.owner_id != user_id:
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
    from models.alert import Alert
    from models.reading import Telemetry
    from models.session import RecordingSession

    p = get_plant(db, plant_id)
    if not p:
        return False
    if user_id is not None and p.owner_id is not None and p.owner_id != user_id:
        return False
    db.query(Alert).filter(Alert.plant_id == plant_id).delete(synchronize_session=False)
    db.query(PlantControl).filter(PlantControl.plant_id == plant_id).delete(synchronize_session=False)
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
    if user_id is not None and p.owner_id is not None and p.owner_id != user_id:
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
    """Cascading delete plants for ``user_id`` (required — that user's samples only)."""
    if user_id is None:
        return 0
    ids = [p.id for p in list_plants(db, owner_id=user_id)]
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
