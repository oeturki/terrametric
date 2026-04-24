"""
FR3 - Threshold alerts: list live / active (unacknowledged) for the UI.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from models.alert import Alert

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
):
    """
    Unacknowledged alerts for the notification bell. Each item includes a stable ``id`` so
    the frontend can de-duplicate toasts on polling.
    """
    q = db.query(Alert).filter(Alert.acknowledged.is_(False))
    if plant_id is not None:
        q = q.filter(Alert.plant_id == plant_id)
    rows = q.order_by(Alert.created_at.desc()).limit(limit).all()
    return [_alert_to_ui(a) for a in rows]


@router.post("/{alert_id}/ack")
def acknowledge_alert(alert_id: int, db: Session = Depends(get_db)):
    a = db.query(Alert).filter(Alert.id == alert_id).first()
    if not a:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Alert not found")
    a.acknowledged = True
    db.commit()
    return {"status": "ok", "id": alert_id}
