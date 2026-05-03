"""
Auto-activate ventilation when temp/humidity leave the desired [min,max] band
(and auto-off when they recover), only during an active recording session.

Separate from threshold *warnings* (`warn_low` / `warn_high` in alerts).
Uses the same POST body as Home: ``{ on, spin }`` via ``pi_ventilation_client``.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from config import settings
from models.reading import Telemetry
import services.plant_control_service as pc_svc
from services.pi_ventilation_client import pi_ventilation_configured, post_ventilation_json
from services.recording_session_service import get_open_session_for_plant

logger = logging.getLogger(__name__)

# ── Manual vs auto semantics (single-process; same model as threshold_service _state)
_auto_driven_on: bool = False
_suppress_auto_until_recovery: bool = False
_last_auto_trigger_plant_id: Optional[int] = None

# (plant_id, session_id) -> {"in_breach": bool}
_breach_edges: Dict[Tuple[int, int], Dict[str, bool]] = {}


def reset_state_for_tests() -> None:
    """Clear process-local latch state (pytest only)."""
    global _auto_driven_on, _suppress_auto_until_recovery, _last_auto_trigger_plant_id
    _auto_driven_on = False
    _suppress_auto_until_recovery = False
    _last_auto_trigger_plant_id = None
    _breach_edges.clear()


def notify_manual_vent_success(*, turn_on: bool) -> None:
    """Call after Pi accepted an authenticated UI ventilation command."""
    global _auto_driven_on, _suppress_auto_until_recovery
    _auto_driven_on = False
    if turn_on:
        _suppress_auto_until_recovery = False
    else:
        _suppress_auto_until_recovery = True


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


def _row_desired_breach(profile: Dict[str, Any], row: Telemetry) -> bool:
    t = row.temperature
    if t is not None:
        b = _get_band(profile, "temperature")
        if not _in_numeric_band(float(t), b.get("min"), b.get("max")):
            return True
    h = row.humidity
    if h is not None:
        b = _get_band(profile, "humidity")
        if not _in_numeric_band(float(h), b.get("min"), b.get("max")):
            return True
    return False


def _row_evidence_inside_desired(profile: Dict[str, Any], row: Telemetry) -> bool:
    """True only when both present channels (if any) are inside desired min/max."""
    if row.temperature is None and row.humidity is None:
        return False
    t = row.temperature
    if t is not None:
        b = _get_band(profile, "temperature")
        if not _in_numeric_band(float(t), b.get("min"), b.get("max")):
            return False
    h = row.humidity
    if h is not None:
        b = _get_band(profile, "humidity")
        if not _in_numeric_band(float(h), b.get("min"), b.get("max")):
            return False
    return True


def _post_vent(on: bool) -> None:
    payload = {"on": True, "spin": True} if on else {"on": False, "spin": False}
    r = post_ventilation_json(payload)
    if r.status_code != 200:
        detail = r.text[:500] if r.text else str(r.status_code)
        raise RuntimeError(f"Pi ventilation returned {r.status_code}: {detail}")


def reconcile_auto_ventilation_after_profile_save(db: Session, plant_id: int) -> None:
    """Re-evaluate ventilation after Control Variables saved (desired band may have moved)."""
    sess = get_open_session_for_plant(db, plant_id)
    if sess is None:
        return
    row = (
        db.query(Telemetry)
        .filter(Telemetry.plant_id == plant_id, Telemetry.session_id == sess.id)
        .order_by(Telemetry.timestamp.desc(), Telemetry.id.desc())
        .first()
    )
    if row is None:
        return
    process_auto_ventilation_after_commit(
        db, plant_id=plant_id, session_id=sess.id, row=row
    )


def process_auto_ventilation_after_commit(
    db: Session,
    *,
    plant_id: Optional[int],
    session_id: Optional[int],
    row: Telemetry,
) -> None:
    global _auto_driven_on, _suppress_auto_until_recovery, _last_auto_trigger_plant_id

    pid = plant_id
    sid = session_id

    # Only evaluate during active recordings (see plan).
    if pid is None or sid is None:
        return

    profile = pc_svc.get_control_dict_for_plant(db, pid)
    if profile is None:
        return

    # Suppress-clear path can run without Pi reachable (logical recovery).
    if (
        _suppress_auto_until_recovery
        and pid == _last_auto_trigger_plant_id
        and _row_evidence_inside_desired(profile, row)
    ):
        _suppress_auto_until_recovery = False

    if not settings.AUTO_VENTILATION_ENABLED:
        return
    if not pi_ventilation_configured():
        return

    breach_now = _row_desired_breach(profile, row)
    key = (pid, sid)
    st = _breach_edges.setdefault(key, {"in_breach": False})
    prev_breach = bool(st["in_breach"])

    try:
        if breach_now:
            if not prev_breach and not _suppress_auto_until_recovery:
                _post_vent(True)
                _auto_driven_on = True
                _last_auto_trigger_plant_id = pid
                logger.info(
                    "auto ventilation ON (desired band breach) plant_id=%s session_id=%s",
                    pid,
                    sid,
                )
            st["in_breach"] = True
        else:
            if prev_breach and _auto_driven_on:
                _post_vent(False)
                _auto_driven_on = False
                logger.info(
                    "auto ventilation OFF (back inside desired band) plant_id=%s session_id=%s",
                    pid,
                    sid,
                )
            st["in_breach"] = False
    except Exception:
        logger.exception(
            "auto ventilation Pi command failed plant_id=%s session_id=%s breach=%s",
            pid,
            sid,
            breach_now,
        )
