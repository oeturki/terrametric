"""Notify the UI (via persisted ``Alert`` rows) when a gallery capture is saved."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from models.alert import Alert
from models.plant import Plant

logger = logging.getLogger(__name__)


def emit_capture_saved_alert(
    db: Session,
    *,
    plant_id: int,
    session_id: Optional[int],
    trigger: str,
    detail: Optional[str],
) -> None:
    """
    Insert an ``info`` alert so /api/alerts/active and the Home feed show the event.
    Intended for manual snapshots and alert-driven captures — not noisy interval/motion.
    """
    if trigger not in ("manual", "desired_breach", "tolerance_breach", "height_target"):
        return

    try:
        caption = ""
        p = db.query(Plant).filter(Plant.id == plant_id).first()
        if p:
            caption = (p.name or "Sample").strip() or "Sample"
            if (p.qr_code or "").strip():
                caption += f" — {p.qr_code.strip()}"

        detail_text = (detail or "").strip()
        body = detail_text if detail_text else "Camera capture stored."

        if trigger == "manual":
            title = "Manual photo saved"
            message = f"{caption}: camera capture stored. Open the Gallery tab to view."
            variable = "manual_capture"
        elif trigger == "height_target":
            title = "Snapshot saved (height milestone)"
            message = f"{caption}: {body} Open the Gallery tab to view."
            variable = "camera_height_target"
        elif trigger == "tolerance_breach":
            title = "Snapshot saved (tolerance breach)"
            message = f"{caption}: {body} Open the Gallery tab to view."
            variable = "camera_tolerance_breach"
        else:
            title = "Snapshot saved (range breach)"
            message = f"{caption}: {body} Open the Gallery tab to view."
            variable = "camera_desired_breach"

        a = Alert(
            plant_id=plant_id,
            session_id=session_id,
            variable=variable,
            severity="info",
            title=title,
            message=message,
            acknowledged=False,
            created_at=datetime.utcnow(),
        )
        db.add(a)
        db.commit()
    except Exception:
        logger.exception(
            "emit_capture_saved_alert failed plant_id=%s trigger=%s",
            plant_id,
            trigger,
        )
        try:
            db.rollback()
        except Exception:
            pass
