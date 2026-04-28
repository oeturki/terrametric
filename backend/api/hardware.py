"""
Proxy authenticated UI requests to the Raspberry Pi hardware agent
(FastAPI on the Pi, see `pi/hardware_agent.py`).
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from config import settings
from deps.auth import get_current_user
from models.user import User

router = APIRouter()


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
async def hardware_capture(_: User = Depends(get_current_user)):
    base = _require_pi_config()
    url = f"{base}/camera/capture"
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(url, headers=_pi_headers())
    except httpx.ConnectError as e:
        raise HTTPException(status_code=502, detail=f"Cannot reach Pi at {base}: {e!s}") from e
    except httpx.TimeoutException as e:
        raise HTTPException(status_code=504, detail="Pi camera capture timed out") from e

    if r.status_code != 200:
        _raise_unless_pi_ok(r)
    ct = r.headers.get("content-type", "image/jpeg")
    return Response(content=r.content, media_type=ct)


@router.post("/ventilation")
async def hardware_ventilation(
    body: VentilationBody,
    _: User = Depends(get_current_user),
):
    base = _require_pi_config()
    url = f"{base}/ventilation"
    payload = body.model_dump(exclude_none=True)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(url, json=payload, headers=_pi_headers())
    except httpx.ConnectError as e:
        raise HTTPException(status_code=502, detail=f"Cannot reach Pi at {base}: {e!s}") from e
    except httpx.TimeoutException as e:
        raise HTTPException(status_code=504, detail="Pi ventilation command timed out") from e

    if r.status_code != 200:
        _raise_unless_pi_ok(r)
    return r.json()
