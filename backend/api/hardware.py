"""
Proxy authenticated UI requests to the Raspberry Pi hardware agent
(FastAPI on the Pi, see `pi/hardware_agent.py`).
"""

from __future__ import annotations

import asyncio
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from deps.auth import get_current_user
from models.reading import Telemetry
from models.user import User
from services import auto_ventilation_service as auto_vent
from services import camera_service as cam_svc
from services.capture_alert_service import emit_capture_saved_alert
from services.pi_camera_client import fetch_pi_camera_jpeg
from services.pi_ventilation_client import post_ventilation_json
from services.recording_session_service import get_open_recording_session_for_user

router = APIRouter()
_log = logging.getLogger(__name__)


def _pi_headers() -> dict[str, str]:
    h: dict[str, str] = {}
    if settings.HARDWARE_PI_KEY:
        h["X-Device-Key"] = settings.HARDWARE_PI_KEY
    return h


def _require_pi_config() -> str:
    base = (settings.HARDWARE_PI_BASE or "").strip().rstrip("/")
    if not base:
        raise HTTPException(
            status_code=503,
            detail="Pi hardware is not configured. Set HARDWARE_PI_BASE and HARDWARE_PI_KEY in backend .env",
        )
    if not settings.HARDWARE_PI_KEY:
        raise HTTPException(
            status_code=503,
            detail="HARDWARE_PI_KEY is not set. It must match DEVICE_KEY on the Pi agent.",
        )
    return base


def _raise_unless_pi_ok(r: httpx.Response) -> None:
    """Map Pi proxy errors to FastAPI HTTPException (better copy for device-key mismatch)."""
    if r.status_code == 200:
        return
    detail = r.text[:2000] if r.text else f"status {r.status_code}"
    if r.status_code == 401:
        try:
            j = r.json()
            if isinstance(j, dict) and str(j.get("detail", "")).strip() == "Invalid or missing X-Device-Key":
                raise HTTPException(
                    status_code=502,
                    detail=(
                        "Pi rejected X-Device-Key: set DEVICE_KEY on the Pi (in .env) to exactly match "
                        "HARDWARE_PI_KEY in backend/.env on this laptop, then restart ./start_terrametric_pi.sh."
                    ),
                )
        except HTTPException:
            raise
        except Exception:
            pass
    raise HTTPException(status_code=502, detail=f"Pi error: {detail}")


class VentilationBody(BaseModel):
    on: bool | None = None
    angle: float | None = None
    # Forwarded to Pi: True = sweep motion on "ventilation" click; False = hold 90° only
    spin: bool = True


@router.post("/capture")
async def hardware_capture(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_pi_config()
    try:
        jpeg = await asyncio.to_thread(fetch_pi_camera_jpeg, timeout_sec=60.0)
    except RuntimeError as e:
        msg = str(e)
        low = msg.lower()
        if "not configured" in low:
            raise HTTPException(status_code=503, detail=msg) from e
        if "timed out" in low or "timeout" in low:
            raise HTTPException(status_code=504, detail=msg) from e
        raise HTTPException(status_code=502, detail=msg) from e
    sess = get_open_recording_session_for_user(db, user.id)
    capture_persisted = False
    if sess is not None and jpeg:
        tr = (
            db.query(Telemetry)
            .filter(Telemetry.plant_id == sess.plant_id)
            .order_by(Telemetry.timestamp.desc(), Telemetry.id.desc())
            .first()
        )
        h = None
        tid = None
        if tr:
            tid = tr.id
            if tr.plant_height is not None:
                h = float(tr.plant_height)
            elif tr.distance is not None:
                h = float(tr.distance)
        try:
            cam_svc.save_capture(
                db,
                plant_id=sess.plant_id,
                session_id=sess.id,
                telemetry_id=tid,
                trigger="manual",
                detail=None,
                jpeg_bytes=jpeg,
                height_cm=h,
            )
            emit_capture_saved_alert(
                db,
                plant_id=sess.plant_id,
                session_id=sess.id,
                trigger="manual",
                detail=None,
            )
            capture_persisted = True
        except Exception:
            _log.exception("persist manual camera capture failed")

    headers = {}
    if capture_persisted:
        headers["X-Capture-Persisted"] = "1"
    return Response(content=jpeg, media_type="image/jpeg", headers=headers)

@router.post("/ventilation")
async def hardware_ventilation(
    body: VentilationBody,
    _: User = Depends(get_current_user),
):
    base = _require_pi_config()
    payload = body.model_dump(exclude_none=True)
    try:
        r = await asyncio.to_thread(post_ventilation_json, payload)
    except httpx.ConnectError as e:
        raise HTTPException(status_code=502, detail=f"Cannot reach Pi at {base}: {e!s}") from e
    except httpx.TimeoutException as e:
        raise HTTPException(status_code=504, detail="Pi ventilation command timed out") from e

    if r.status_code != 200:
        _raise_unless_pi_ok(r)
    # Keep auto-vent state aligned with intentional on/off clicks (Home toggles send explicit ``on``).
    if body.on is not None:
        auto_vent.notify_manual_vent_success(turn_on=bool(body.on))
    return r.json()
