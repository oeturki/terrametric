"""
Synchronous POST to Pi ``/camera/capture`` (JPEG bytes). Shared by hardware proxy and server-side triggers.
"""

from __future__ import annotations

import httpx

from config import settings


def _strip_base() -> str:
    return (settings.HARDWARE_PI_BASE or "").strip().rstrip("/")


def pi_camera_configured() -> bool:
    return bool(_strip_base() and (settings.HARDWARE_PI_KEY or "").strip())


def fetch_pi_camera_jpeg(*, timeout_sec: float = 60.0) -> bytes:
    base = _strip_base()
    key = (settings.HARDWARE_PI_KEY or "").strip()
    if not base or not key:
        raise RuntimeError("Pi hardware not configured for camera")
    url = f"{base}/camera/capture"
    headers = {"X-Device-Key": key}
    try:
        with httpx.Client(timeout=timeout_sec) as client:
            r = client.post(url, headers=headers)
    except httpx.ConnectError as e:
        raise RuntimeError(f"Cannot reach Pi camera: {e}") from e
    except httpx.TimeoutException:
        raise RuntimeError("Pi camera capture timed out")
    if r.status_code != 200:
        detail = r.text[:500] if r.text else str(r.status_code)
        raise RuntimeError(f"Pi camera error {r.status_code}: {detail}")
    return r.content
