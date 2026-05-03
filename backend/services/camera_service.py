"""
Persist Pi camera JPEG captures and list them per plant (sample) for the Gallery.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from config import settings
from models.plant import Plant
from models.plant_capture import PlantCapture


def storage_root() -> Path:
    raw = (settings.CAPTURE_STORAGE_DIR or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path(__file__).resolve().parent.parent / "data" / "captures").resolve()


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def save_capture(
    db: Session,
    *,
    plant_id: int,
    session_id: Optional[int],
    telemetry_id: Optional[int],
    trigger: str,
    detail: Optional[str],
    jpeg_bytes: bytes,
    height_cm: Optional[float] = None,
) -> PlantCapture:
    root = storage_root()
    ext = ".jpg"
    fname = f"{uuid.uuid4().hex}{ext}"
    rel = f"{plant_id}/{fname}"
    abs_path = root / str(plant_id) / fname
    _ensure_parent(abs_path)
    abs_path.write_bytes(jpeg_bytes)

    row = PlantCapture(
        plant_id=plant_id,
        session_id=session_id,
        telemetry_id=telemetry_id,
        created_at=datetime.now(timezone.utc),
        trigger=trigger,
        detail=(detail[:1500] if detail else None),
        storage_path=rel.replace("\\", "/"),
        height_cm=height_cm,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_captures_json_for_plants(
    db: Session,
    plant_ids: List[int],
    *,
    plant_id_filter: Optional[int] = None,
) -> List[Dict[str, Any]]:
    if not plant_ids:
        return []
    q = db.query(PlantCapture, Plant.qr_code, Plant.name).join(Plant, PlantCapture.plant_id == Plant.id)
    q = q.filter(PlantCapture.plant_id.in_(plant_ids))
    if plant_id_filter is not None:
        q = q.filter(PlantCapture.plant_id == plant_id_filter)
    rows = q.order_by(PlantCapture.created_at.desc(), PlantCapture.id.desc()).all()
    out: List[Dict[str, Any]] = []
    for cap, qr, name in rows:
        ts = cap.created_at
        if ts and ts.tzinfo is None:
            ts_iso = ts.replace(tzinfo=timezone.utc).isoformat()
        else:
            ts_iso = ts.isoformat() if ts else ""
        out.append(
            {
                "id": cap.id,
                "plant_id": cap.plant_id,
                "session_id": cap.session_id,
                "sample_qr": qr or "unknown",
                "plant_name": name,
                "timestamp": ts_iso,
                "height_cm": cap.height_cm,
                "trigger": cap.trigger,
                "detail": cap.detail,
                "image_url": f"/api/camera/images/{cap.id}/file",
            }
        )
    return out


def get_capture_for_owner(db: Session, capture_id: int, owner_user_id: int) -> Optional[PlantCapture]:
    row = (
        db.query(PlantCapture)
        .join(Plant, PlantCapture.plant_id == Plant.id)
        .filter(PlantCapture.id == capture_id, Plant.owner_id == owner_user_id)
        .first()
    )
    return row


def absolute_file_path(capture: PlantCapture) -> Path:
    p = (storage_root() / capture.storage_path).resolve()
    root = storage_root().resolve()
    try:
        p.relative_to(root)
    except ValueError:
        raise ValueError("invalid capture path")
    return p
