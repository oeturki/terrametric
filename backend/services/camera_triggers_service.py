"""Server-side camera triggers after telemetry ingest: interval, desired-band breach, motion edge."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from models.plant_capture import PlantCapture
from models.reading import Telemetry
import services.plant_control_service as pc_svc
from services import camera_service as cam_svc
from services.pi_camera_client import fetch_pi_camera_jpeg, pi_camera_configured

logger = logging.getLogger(__name__)

COOLDOWN_SEC = 120.0

# (plant_id, session_id) -> monotonic timestamp of last auto capture for breach channel
_desired_breach_last: Dict[Tuple[int, int], float] = {}
_motion_last: Dict[Tuple[int, int], float] = {}
_motion_prev_movement: Dict[Tuple[int, int], Optional[bool]] = {}


def _get_band(profile: Dict[str, Any], key: str) -> Dict[str, Any]:
    return (profile or {}).get(key) or {}


def _in_numeric_band(value: float, lo: Any, hi: Any) -> bool:
    if lo is None and hi is None:
        return True
    if lo is not None and value < float(lo):
        return False
    if hi is not None and value > float(hi):
        return False
    return True


def _desired_breach_labels(profile: Dict[str, Any], row: Telemetry) -> list[str]:
    out: list[str] = []
    t = row.temperature
    if t is not None:
        b = _get_band(profile, "temperature")
        if not _in_numeric_band(float(t), b.get("min"), b.get("max")):
            out.append("temperature")
    h = row.humidity
    if h is not None:
        b = _get_band(profile, "humidity")
        if not _in_numeric_band(float(h), b.get("min"), b.get("max")):
            out.append("humidity")
    light = row.light
    if light is not None:
        b = _get_band(profile, "light")
        if not _in_numeric_band(float(light), b.get("min"), b.get("max")):
            out.append("light")
    return out


def _height_from_row(row: Telemetry) -> Optional[float]:
    if row.plant_height is not None:
        return float(row.plant_height)
    if row.distance is not None:
        return float(row.distance)
    return None


def maybe_capture_after_telemetry(db: Session, row: Telemetry, plant_id: int, session_id: int) -> None:
    """Run after telemetry row committed (``row.id`` set). Best-effort; logs errors."""
    if not pi_camera_configured():
        return
    profile = pc_svc.get_control_dict_for_plant(db, plant_id)
    if profile is None:
        return
    cam = profile.get("camera") or {}
    pkey = (plant_id, session_id)

    interval_minutes = int(cam.get("interval") or 0)
    if interval_minutes > 0:
        interval_sec = max(interval_minutes * 60, 30)
        last = (
            db.query(PlantCapture)
            .filter(
                PlantCapture.plant_id == plant_id,
                PlantCapture.session_id == session_id,
                PlantCapture.trigger == "interval",
            )
            .order_by(PlantCapture.created_at.desc())
            .first()
        )
        need = True
        if last and last.created_at:
            lu = last.created_at
            if lu.tzinfo is None:
                lu = lu.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - lu).total_seconds()
            if age < interval_sec:
                need = False
        if need:
            try:
                jpeg = fetch_pi_camera_jpeg(timeout_sec=45.0)
                cam_svc.save_capture(
                    db,
                    plant_id=plant_id,
                    session_id=session_id,
                    telemetry_id=row.id,
                    trigger="interval",
                    detail=None,
                    jpeg_bytes=jpeg,
                    height_cm=_height_from_row(row),
                )
            except Exception:
                logger.exception("interval camera capture failed plant_id=%s", plant_id)

    if cam.get("on_alert"):
        labels = _desired_breach_labels(profile, row)
        if labels:
            now_m = time.monotonic()
            last_m = _desired_breach_last.get(pkey, 0.0)
            if now_m - last_m >= COOLDOWN_SEC:
                _desired_breach_last[pkey] = now_m
                try:
                    jpeg = fetch_pi_camera_jpeg(timeout_sec=45.0)
                    cam_svc.save_capture(
                        db,
                        plant_id=plant_id,
                        session_id=session_id,
                        telemetry_id=row.id,
                        trigger="desired_breach",
                        detail=",".join(labels),
                        jpeg_bytes=jpeg,
                        height_cm=_height_from_row(row),
                    )
                except Exception:
                    logger.exception("desired breach capture failed plant_id=%s", plant_id)

    if cam.get("on_motion") and row.movement is not None:
        cur = bool(row.movement)
        prev = _motion_prev_movement.get(pkey)
        _motion_prev_movement[pkey] = cur
        edge_up = prev is False and cur is True
        if edge_up:
            now_m = time.monotonic()
            last_m = _motion_last.get(pkey, 0.0)
            if now_m - last_m >= COOLDOWN_SEC:
                _motion_last[pkey] = now_m
                try:
                    jpeg = fetch_pi_camera_jpeg(timeout_sec=45.0)
                    cam_svc.save_capture(
                        db,
                        plant_id=plant_id,
                        session_id=session_id,
                        telemetry_id=row.id,
                        trigger="motion",
                        detail="pir",
                        jpeg_bytes=jpeg,
                        height_cm=_height_from_row(row),
                    )
                except Exception:
                    logger.exception("motion capture failed plant_id=%s", plant_id)


def reset_triggers_for_tests() -> None:
    _desired_breach_last.clear()
    _motion_last.clear()
    _motion_prev_movement.clear()
