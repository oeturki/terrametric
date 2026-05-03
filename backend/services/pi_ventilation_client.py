"""
Synchronous POST to the Pi hardware agent ``/ventilation`` endpoint.

Shared by the authenticated API proxy (`api/hardware.py`) and auto-ventilation
so payloads match exactly what Home sends (`on` / `spin`).
"""

from __future__ import annotations

from typing import Any, Dict

import httpx

from config import settings


def _strip_base() -> str:
    return (settings.HARDWARE_PI_BASE or "").strip().rstrip("/")


def pi_ventilation_configured() -> bool:
    return bool(_strip_base() and (settings.HARDWARE_PI_KEY or "").strip())


def post_ventilation_json(payload: Dict[str, Any], *, timeout_sec: float = 15.0) -> httpx.Response:
    """
    POST JSON to `{HARDWARE_PI_BASE}/ventilation` with ``X-Device-Key``.
    Caller must verify config first (or tolerate RuntimeError for misconfiguration).
    """
    base = _strip_base()
    key = (settings.HARDWARE_PI_KEY or "").strip()
    if not base or not key:
        raise RuntimeError("Pi ventilation not configured")
    url = f"{base}/ventilation"
    headers = {"X-Device-Key": key}
    with httpx.Client(timeout=timeout_sec) as client:
        return client.post(url, json=payload, headers=headers)
