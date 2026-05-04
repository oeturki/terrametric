"""
FR3 - Threshold alerts: list live / active (unacknowledged) for the UI.
Scoped to the authenticated user's plants unless ``plant_id`` is set (must be owned).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from deps.auth import get_current_user
from models.alert import Alert
from models.plant import Plant
from models.user import User

router = APIRouter()


def _alert_to_ui(a: Alert) -> dict[str, Any]:
    sev = a.severity if a.severity in ("warning", "danger", "info") else "warning"
    title = a.title or f"{a.variable} alert"
    ts = a.created_at.isoformat() if a.created_at else datetime.utcnow().isoformat()
    return {
        "id": a.id,
        "severity": sev,
        "title": title,
        "message": a.message or "",
        "variable": a.variable,
        "plant_id": a.plant_id,
        "session_id": a.session_id,
        "timestamp": ts,
        "acknowledged": a.acknowledged,
    }


@router.get("/active", response_model=List[dict])
def get_active_alerts(
    plant_id: Optional[int] = Query(None, description="If set, only alerts for this sample"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Unacknowledged alerts for the notification bell. Each item includes a stable ``id`` so
    the frontend can de-duplicate toasts on polling.
    """
    my_ids = [r[0] for r in db.query(Plant.id).filter(Plant.owner_id == user.id).all()]
    if not my_ids:
        return []
    q = db.query(Alert).filter(Alert.acknowledged.is_(False), Alert.plant_id.in_(my_ids))
    if plant_id is not None:
        owner_ok = db.query(Plant.id).filter(Plant.id == plant_id, Plant.owner_id == user.id).first()
        if not owner_ok:
            raise HTTPException(status_code=404, detail="Plant not found")
        q = q.filter(Alert.plant_id == plant_id)
    rows = q.order_by(Alert.created_at.desc()).limit(limit).all()
    return [_alert_to_ui(a) for a in rows]


class AckAlertsBatchBody(BaseModel):
    ids: List[Any] = Field(default_factory=list, max_length=500)


def _positive_alert_ids(raw: List[Any]) -> Set[int]:
    """Coerce alert ids after JSON parsing (avoid relying on isinstance(..., int) only)."""
    out: Set[int] = set()
    for x in raw:
        try:
            n = int(x)
        except (TypeError, ValueError):
            continue
        if n > 0:
            out.add(n)
    return out


@router.post("/ack-batch")
def acknowledge_alerts_batch(
    body: AckAlertsBatchBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Mark many alerts acknowledged in one transaction. Only alerts for plants owned by
    the user are updated; ids that are missing, foreign, or already acknowledged count
    as no-ops without error.
    """
    my_ids = [r[0] for r in db.query(Plant.id).filter(Plant.owner_id == user.id).all()]
    if not my_ids:
        return {"status": "ok", "acknowledged_count": 0, "requested": 0}
    id_set = _positive_alert_ids(list(body.ids))
    if not id_set:
        return {"status": "ok", "acknowledged_count": 0, "requested": 0}
    rows = (
        db.query(Alert)
        .filter(
            Alert.id.in_(id_set),
            Alert.plant_id.in_(my_ids),
            Alert.acknowledged.is_(False),
        )
        .all()
    )
    for a in rows:
        a.acknowledged = True
    db.commit()
    return {"status": "ok", "acknowledged_count": len(rows), "requested": len(id_set)}


@router.post("/{alert_id}/ack")
def acknowledge_alert(alert_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    a = db.query(Alert).filter(Alert.id == alert_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Alert not found")
    p = db.query(Plant).filter(Plant.id == a.plant_id).first()
    if not p or p.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Alert not found")
    a.acknowledged = True
    db.commit()
    return {"status": "ok", "id": alert_id}
