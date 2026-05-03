"""Server-side camera triggers after telemetry ingest: interval, height milestone, tolerance/desired breach, motion edge."""

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
from services.capture_alert_service import emit_capture_saved_alert
from services.pi_camera_client import fetch_pi_camera_jpeg, pi_camera_configured

logger = logging.getLogger(__name__)

COOLDOWN_SEC = 120.0

# Keyed by (plant_id, session_or_sentinel); sentinel -1 = no open recording session on row.
_desired_breach_last: Dict[Tuple[int, int], float] = {}
_motion_last: Dict[Tuple[int, int], float] = {}
_motion_prev_movement: Dict[Tuple[int, int], Optional[bool]] = {}


def _capture_state_key(plant_id: int, session_id: Optional[int]) -> Tuple[int, int]:
    """Process-local cooldown keys; -1 = telemetry row without an open recording session."""
    return (plant_id, session_id if session_id is not None else -1)


def _latest_capture_for_trigger(
    db: Session,
    *,
    plant_id: int,
    session_id: Optional[int],
    trigger: str,
) -> Optional[PlantCapture]:
    q = db.query(PlantCapture).filter(
        PlantCapture.plant_id == plant_id,
        PlantCapture.trigger == trigger,
    )
    if session_id is not None:
        q = q.filter(PlantCapture.session_id == session_id)
    else:
        q = q.filter(PlantCapture.session_id.is_(None))
    return q.order_by(PlantCapture.created_at.desc(), PlantCapture.id.desc()).first()


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


def _optional_numeric_bound(v: Any):
    """Coerce control profile scalar to float bound, else None."""
    if v is None:
        return None
    if isinstance(v, str) and not str(v).strip():
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _desired_breach_labels(profile: Dict[str, Any], row: Telemetry) -> list[str]:
    """Reading outside desired min/max on temperature / humidity / light."""
    out: list[str] = []
    t = row.temperature
    if t is not None:
        b = _get_band(profile, "temperature")
        lo = _optional_numeric_bound(b.get("min"))
        hi = _optional_numeric_bound(b.get("max"))
        if lo is not None or hi is not None:
            if not _in_numeric_band(float(t), lo, hi):
                out.append("temperature")
    h = row.humidity
    if h is not None:
        b = _get_band(profile, "humidity")
        lo = _optional_numeric_bound(b.get("min"))
        hi = _optional_numeric_bound(b.get("max"))
        if lo is not None or hi is not None:
            if not _in_numeric_band(float(h), lo, hi):
                out.append("humidity")
    light = row.light
    if light is not None:
        b = _get_band(profile, "light")
        lo = _optional_numeric_bound(b.get("min"))
        hi = _optional_numeric_bound(b.get("max"))
        if lo is not None or hi is not None:
            if not _in_numeric_band(float(light), lo, hi):
                out.append("light")
    return out


def _soft_tolerance_hi(band: Dict[str, Any]):
    hi = band.get("warn_high")
    if hi is None:
        hi = band.get("warn")
    return hi


def _tolerance_breach_labels(profile: Dict[str, Any], row: Telemetry) -> list[str]:
    """Tolerance (soft warn) breaches for temperature, humidity, and light only."""
    out: list[str] = []
    t = row.temperature
    if t is not None:
        b = _get_band(profile, "temperature")
        lo, hi = b.get("warn_low"), _soft_tolerance_hi(b)
        if lo is not None or hi is not None:
            if not _in_numeric_band(float(t), lo, hi):
                out.append("temperature")
    h = row.humidity
    if h is not None:
        b = _get_band(profile, "humidity")
        lo, hi = b.get("warn_low"), _soft_tolerance_hi(b)
        if lo is not None or hi is not None:
            if not _in_numeric_band(float(h), lo, hi):
                out.append("humidity")
    light = row.light
    if light is not None:
        b = _get_band(profile, "light")
        lo, hi = b.get("warn_low"), _soft_tolerance_hi(b)
        if lo is not None or hi is not None:
            if not _in_numeric_band(float(light), lo, hi):
                out.append("light")
    return out


def _tolerance_band_caption(lo: Any, hi: Any, unit_suffix: str) -> str:
    if lo is None and hi is None:
        return "(tolerance band not fully set{})".format(unit_suffix)
    if lo is not None and hi is not None:
        return f"{float(lo):.1f}–{float(hi):.1f}{unit_suffix}"
    if lo is not None:
        return f"low ≥ {float(lo):.1f}{unit_suffix}"
    return f"high ≤ {float(hi):.1f}{unit_suffix}"


def format_tolerance_breach_detail(profile: Dict[str, Any], row: Telemetry, labels: list[str]) -> str:
    """Sentences aligned with persisted threshold alerts / UI tolerance bands."""
    lines: list[str] = []
    for axis in labels:
        if axis == "temperature":
            t = row.temperature
            if t is None:
                continue
            b = _get_band(profile, "temperature")
            lo, hi = b.get("warn_low"), _soft_tolerance_hi(b)
            tv = float(t)
            cap = _tolerance_band_caption(lo, hi, " °C")
            if lo is not None and tv < float(lo):
                lines.append(f"Temperature {tv:.1f} °C is below the tolerance low bound {float(lo):.1f} °C (band {cap}).")
            elif hi is not None and tv > float(hi):
                lines.append(f"Temperature {tv:.1f} °C is above the tolerance high bound {float(hi):.1f} °C (band {cap}).")
            else:
                lines.append(f"Temperature {tv:.1f} °C is outside the tolerance band {cap}.")
        elif axis == "humidity":
            h = row.humidity
            if h is None:
                continue
            b = _get_band(profile, "humidity")
            lo, hi = b.get("warn_low"), _soft_tolerance_hi(b)
            hv = float(h)
            cap = _tolerance_band_caption(lo, hi, "% RH")
            if lo is not None and hv < float(lo):
                lines.append(f"Humidity {hv:.1f}% RH is below the tolerance low bound {float(lo):.1f}% (band {cap}).")
            elif hi is not None and hv > float(hi):
                lines.append(f"Humidity {hv:.1f}% RH is above the tolerance high bound {float(hi):.1f}% (band {cap}).")
            else:
                lines.append(f"Humidity {hv:.1f}% RH is outside the tolerance band {cap}.")
        elif axis == "light":
            lg = row.light
            if lg is None:
                continue
            b = _get_band(profile, "light")
            lo, hi = b.get("warn_low"), _soft_tolerance_hi(b)
            lv = float(lg)
            cap = _tolerance_band_caption(lo, hi, " lux")
            if lo is not None and lv < float(lo):
                lines.append(f"Light {lv:.0f} lux is below the tolerance low bound {float(lo):.0f} lux (band {cap}).")
            elif hi is not None and lv > float(hi):
                lines.append(f"Light {lv:.0f} lux is above the tolerance high bound {float(hi):.0f} lux (band {cap}).")
            else:
                lines.append(f"Light {lv:.0f} lux is outside the tolerance band {cap}.")
    return (
        "\n".join(lines)
        if lines
        else "Reading outside tolerance thresholds (see Control Variables)."
    )


def _height_from_row(row: Telemetry) -> Optional[float]:
    if row.plant_height is not None:
        return float(row.plant_height)
    if row.distance is not None:
        return float(row.distance)
    return None


def _band_display_text(lo: Any, hi: Any, unit_suffix: str) -> str:
    """Human-readable desired band for copy (e.g. ``4.0–9.0 °C``)."""
    if lo is None and hi is None:
        return f"(no min/max set{unit_suffix})"
    if lo is not None and hi is not None:
        return f"{float(lo):.1f}–{float(hi):.1f}{unit_suffix}"
    if lo is not None:
        return f"min {float(lo):.1f}{unit_suffix}"
    return f"max {float(hi):.1f}{unit_suffix}"


def format_desired_breach_detail(profile: Dict[str, Any], row: Telemetry, labels: list[str]) -> str:
    """
    One sentence per breached axis using live telemetry and saved desired min/max.
    Lines separated by newline for Gallery / alerts.
    """
    lines: list[str] = []
    for axis in labels:
        if axis == "temperature":
            t = row.temperature
            if t is None:
                continue
            b = _get_band(profile, "temperature")
            lo, hi = b.get("min"), b.get("max")
            tv = float(t)
            band_txt = _band_display_text(lo, hi, " °C")
            if lo is not None and tv < float(lo):
                lines.append(
                    f"Temperature {tv:.1f} °C is below the desired minimum {float(lo):.1f} °C "
                    f"(desired band {band_txt})."
                )
            elif hi is not None and tv > float(hi):
                lines.append(
                    f"Temperature {tv:.1f} °C is above the desired maximum {float(hi):.1f} °C "
                    f"(desired band {band_txt})."
                )
            else:
                lines.append(f"Temperature {tv:.1f} °C is outside the desired band {band_txt}.")
        elif axis == "humidity":
            h = row.humidity
            if h is None:
                continue
            b = _get_band(profile, "humidity")
            lo, hi = b.get("min"), b.get("max")
            hv = float(h)
            band_txt = _band_display_text(lo, hi, "% RH")
            if lo is not None and hv < float(lo):
                lines.append(
                    f"Humidity {hv:.1f}% RH is below the desired minimum {float(lo):.1f}% RH "
                    f"(desired band {band_txt})."
                )
            elif hi is not None and hv > float(hi):
                lines.append(
                    f"Humidity {hv:.1f}% RH is above the desired maximum {float(hi):.1f}% RH "
                    f"(desired band {band_txt})."
                )
            else:
                lines.append(f"Humidity {hv:.1f}% RH is outside the desired band {band_txt}.")
        elif axis == "light":
            lg = row.light
            if lg is None:
                continue
            b = _get_band(profile, "light")
            lo, hi = b.get("min"), b.get("max")
            lv = float(lg)
            band_txt = _band_display_text(lo, hi, " lux")
            if lo is not None and lv < float(lo):
                lines.append(
                    f"Light {lv:.0f} lux is below the desired minimum {float(lo):.0f} lux "
                    f"(desired band {band_txt})."
                )
            elif hi is not None and lv > float(hi):
                lines.append(
                    f"Light {lv:.0f} lux is above the desired maximum {float(hi):.0f} lux "
                    f"(desired band {band_txt})."
                )
            else:
                lines.append(f"Light {lv:.0f} lux is outside the desired band {band_txt}.")
    return "\n".join(lines) if lines else "Reading outside desired min/max (see Control Variables)."


def maybe_capture_after_telemetry(db: Session, row: Telemetry, plant_id: int, session_id: Optional[int]) -> None:
    """Run after telemetry row committed (``row.id`` set). Best-effort; ``session_id`` may be None (bridge/backfill)."""
    if not pi_camera_configured():
        return
    profile = pc_svc.get_control_dict_for_plant(db, plant_id)
    if profile is None:
        return
    cam = profile.get("camera") or {}
    pkey = _capture_state_key(plant_id, session_id)

    interval_minutes = int(cam.get("interval") or 0)
    if interval_minutes > 0:
        interval_sec = max(interval_minutes * 60, 30)
        last = _latest_capture_for_trigger(db, plant_id=plant_id, session_id=session_id, trigger="interval")
        need = True
        if last and last.created_at:
            lu = last.created_at
            if lu.tzinfo is None:
                lu = lu.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - lu).total_seconds()
            if age < interval_sec:
                need = False
        if need:
            interval_detail = f"every {interval_minutes} minutes"
            try:
                jpeg = fetch_pi_camera_jpeg(timeout_sec=45.0)
                cam_svc.save_capture(
                    db,
                    plant_id=plant_id,
                    session_id=session_id,
                    telemetry_id=row.id,
                    trigger="interval",
                    detail=interval_detail,
                    jpeg_bytes=jpeg,
                    height_cm=_height_from_row(row),
                )
            except Exception:
                logger.exception("interval camera capture failed plant_id=%s", plant_id)

    # One milestone photo per recording session when measured height reaches target_cm (optional).
    hband = _get_band(profile, "height")
    target_raw = hband.get("target_cm")
    if target_raw is not None:
        try:
            tgt = float(target_raw)
        except (TypeError, ValueError):
            tgt = None
        if tgt is not None and tgt > 0:
            hv = _height_from_row(row)
            if hv is not None and float(hv) >= tgt:
                already = _latest_capture_for_trigger(
                    db,
                    plant_id=plant_id,
                    session_id=session_id,
                    trigger="height_target",
                )
                if not already:
                    milestone_detail = (
                        f"Plant reached desired height of {tgt:.1f} cm "
                        f"(measured {float(hv):.1f} cm at capture time)."
                    )
                    try:
                        jpeg_ht = fetch_pi_camera_jpeg(timeout_sec=45.0)
                        cam_svc.save_capture(
                            db,
                            plant_id=plant_id,
                            session_id=session_id,
                            telemetry_id=row.id,
                            trigger="height_target",
                            detail=milestone_detail,
                            jpeg_bytes=jpeg_ht,
                            height_cm=float(hv),
                        )
                        emit_capture_saved_alert(
                            db,
                            plant_id=plant_id,
                            session_id=session_id,
                            trigger="height_target",
                            detail=milestone_detail,
                        )
                    except Exception:
                        logger.exception("height_target camera capture failed plant_id=%s", plant_id)

    # Environmental snapshots: desired min/max breaches always mirror height milestone behaviour.
    # Tolerance-band breaches snapshot only when camera.on_alert (noisier soft band).
    labels_desired = _desired_breach_labels(profile, row)
    labels_tolerance = _tolerance_breach_labels(profile, row)

    tolerance_snap_allowed = cam.get("on_alert")
    snap_env = bool(labels_desired) or bool(labels_tolerance and tolerance_snap_allowed)

    if snap_env and (labels_desired or labels_tolerance):
        detail_chunks: list[str] = []
        if labels_desired:
            detail_chunks.append(format_desired_breach_detail(profile, row, labels_desired))
        if labels_tolerance and (tolerance_snap_allowed or labels_desired):
            # Include tolerance prose when snapping for tolerance, or alongside a desired breach.
            detail_chunks.append(format_tolerance_breach_detail(profile, row, labels_tolerance))

        breach_detail = "\n\n".join(detail_chunks) if detail_chunks else ""
        if breach_detail.strip():
            now_m = time.monotonic()
            last_m = _desired_breach_last.get(pkey, 0.0)
            if now_m - last_m >= COOLDOWN_SEC:
                _desired_breach_last[pkey] = now_m
                trigger_name = (
                    "desired_breach"
                    if labels_desired
                    else "tolerance_breach"
                )
                try:
                    jpeg = fetch_pi_camera_jpeg(timeout_sec=45.0)
                    cam_svc.save_capture(
                        db,
                        plant_id=plant_id,
                        session_id=session_id,
                        telemetry_id=row.id,
                        trigger=trigger_name,
                        detail=breach_detail,
                        jpeg_bytes=jpeg,
                        height_cm=_height_from_row(row),
                    )
                    emit_capture_saved_alert(
                        db,
                        plant_id=plant_id,
                        session_id=session_id,
                        trigger=trigger_name,
                        detail=breach_detail,
                    )
                except Exception:
                    logger.exception("alert breach capture failed plant_id=%s", plant_id)

    if cam.get("on_motion", True) and row.movement is not None:
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
