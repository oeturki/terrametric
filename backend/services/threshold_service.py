"""
Evaluate sensor readings against per-plant control profiles; create threshold ``Alert`` rows.

Rules (documented):
- For each channel with numeric bounds: breach if value is not None and
  (value < min or value > max) when min/max are set as numbers.
- PIR: movement is cast to 0.0/1.0 and compared to motion.min / motion.max.
- Height: use ``plant_height`` if set, else ``distance`` (ultrasonic cm).
- "Tolerance" (warn) fields are not used for min/max band checks in v1; only [min, max] define the safe band.
  (warn can be used later for soft warnings; omitted here for clarity.)
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from models.alert import Alert
from models.reading import Telemetry
import services.plant_control_service as pc_svc
from services.plant_service import get_plant


def _sample_caption(db: Session, plant_id: int) -> str:
    """Short label for alert text so the user can see which sample the band refers to."""
    p = get_plant(db, plant_id)
    if not p:
        return f"sample id {plant_id}"
    name = (p.name or "").strip() or "Unnamed"
    return f'"{name}" (id {plant_id})'

# (plant_id, variable_name) -> state for edge + cooldown (process-local)
_state: Dict[Tuple[int, str], Dict[str, Any]] = {}

COOLDOWN_SEC = 60.0


def _get_band(profile: Dict[str, Any], key: str) -> Dict[str, Any]:
    return (profile or {}).get(key) or {}


def _in_numeric_band(value: float, lo: Any, hi: Any) -> bool:
    """True = OK (inside [lo, hi]), False = breach. Missing bounds = skip (OK)."""
    if lo is None and hi is None:
        return True
    if lo is not None and value < float(lo):
        return False
    if hi is not None and value > float(hi):
        return False
    return True


def _should_emit(plant_id: int, var: str, now_breached: bool) -> bool:
    key = (plant_id, var)
    st = _state.setdefault(key, {"in_breach": False, "last_emit": 0.0})
    now = time.monotonic()
    if not now_breached:
        st["in_breach"] = False
        return False
    if not st["in_breach"]:
        st["in_breach"] = True
        st["last_emit"] = now
        return True
    if (now - st["last_emit"]) >= COOLDOWN_SEC:
        st["last_emit"] = now
        return True
    return False


def evaluate_telemetry_row(
    db: Session,
    *,
    plant_id: int,
    session_id: Optional[int],
    row: Telemetry,
) -> List[Alert]:
    """Return new Alert ORM objects (already added, not committed)."""
    if plant_id is None:
        return []

    d = pc_svc.get_control_dict_for_plant(db, plant_id)
    if d is None:
        return []

    cap = _sample_caption(db, plant_id)
    new_alerts: List[Alert] = []

    def _emit(
        var: str,
        breach: bool,
        title: str,
        message: str,
    ) -> None:
        if not breach:
            _should_emit(plant_id, var, False)
            return
        if not _should_emit(plant_id, var, True):
            return
        a = Alert(
            plant_id=plant_id,
            session_id=session_id,
            variable=var,
            severity="warning",
            title=title,
            message=message,
            acknowledged=False,
            created_at=datetime.utcnow(),
        )
        db.add(a)
        new_alerts.append(a)

    # --- Temperature ---
    t = row.temperature
    if t is not None:
        b = _get_band(d, "temperature")
        ok = _in_numeric_band(float(t), b.get("min"), b.get("max"))
        _emit(
            "temperature",
            not ok,
            f"Temperature out of range for {cap}",
            f"Sample {cap}. Reading {t:.1f} °C is outside the saved desired band for this sample "
            f"({b.get('min', '?')}-{b.get('max', '?')}) °C. "
            f"If this is unexpected, check Control Variables and that recording / TM_BRIDGE_PLANT_ID matches this id.",
        )

    # --- Humidity ---
    h = row.humidity
    if h is not None:
        b = _get_band(d, "humidity")
        ok = _in_numeric_band(float(h), b.get("min"), b.get("max"))
        _emit(
            "humidity",
            not ok,
            f"Humidity out of range for {cap}",
            f"Sample {cap}. Reading {h:.1f}% is outside the saved desired band "
            f"({b.get('min', '?')}-{b.get('max', '?')}).",
        )

    # --- Light (lux) ---
    light = row.light
    if light is not None:
        b = _get_band(d, "light")
        ok = _in_numeric_band(float(light), b.get("min"), b.get("max"))
        _emit(
            "light",
            not ok,
            f"Light out of range for {cap}",
            f"Sample {cap}. Reading {light:.0f} lux is outside the saved desired band "
            f"({b.get('min', '?')}-{b.get('max', '?')}).",
        )

    # --- Motion: bool -> 0/1 ---
    if row.movement is not None:
        b = _get_band(d, "motion")
        v = 1.0 if row.movement else 0.0
        ok = _in_numeric_band(v, b.get("min"), b.get("max"))
        _emit(
            "motion",
            not ok,
            f"Motion signal out of range for {cap}",
            f"Sample {cap}. PIR value maps to {v:.0f}, outside saved bounds "
            f"({b.get('min', '?')}-{b.get('max', '?')}).",
        )

    # --- Height (cm): prefer plant_height, then distance ---
    hgt = row.plant_height if row.plant_height is not None else row.distance
    if hgt is not None:
        b = _get_band(d, "height")
        ok = _in_numeric_band(float(hgt), b.get("min"), b.get("max"))
        _emit(
            "height",
            not ok,
            f"Height / distance out of range for {cap}",
            f"Sample {cap}. Value {hgt:.1f} cm is outside the saved desired band "
            f"({b.get('min', '?')}-{b.get('max', '?')}).",
        )

    return new_alerts
