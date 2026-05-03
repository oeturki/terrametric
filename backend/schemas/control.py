"""
Per-plant control profile (JSON aligned with frontend/js/config.js getControlData).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class ControlProfilePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    """Body for POST /api/control (plant_id + nested channels)."""

    plant_id: int
    temperature: Optional[Dict[str, Any]] = None
    humidity: Optional[Dict[str, Any]] = None
    light: Optional[Dict[str, Any]] = None
    motion: Optional[Dict[str, Any]] = None
    height: Optional[Dict[str, Any]] = None
    camera: Optional[Dict[str, Any]] = None


class ControlResetBody(BaseModel):
    plant_id: int = Field(..., ge=1)


def _merge_channel(base: Dict[str, Any], patch: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out = dict(base)
    if patch:
        for k, v in patch.items():
            out[k] = v
    return out


def merge_profile_from_payload(
    base: Dict[str, Any],
    body: ControlProfilePayload,
) -> Dict[str, Any]:
    """Deep-merge user payload onto base dict (for POST)."""
    out: Dict[str, Any] = {
        "temperature": _merge_channel(base.get("temperature", {}), body.temperature),
        "humidity": _merge_channel(base.get("humidity", {}), body.humidity),
        "light": _merge_channel(base.get("light", {}), body.light),
        "motion": _merge_channel(base.get("motion", {}), body.motion),
        "height": _merge_channel(base.get("height", {}), body.height),
        "camera": _merge_channel(base.get("camera", {}), body.camera),
    }
    out["height"] = _sanitize_height_channel(out["height"])
    return out


def _sanitize_height_channel(h: Dict[str, Any]) -> Dict[str, Any]:
    """Height is only ``target_cm`` + ``interval``. Strip legacy min/max/warn keys on save."""
    if not h:
        return {"target_cm": None, "interval": 1440}
    tg = h.get("target_cm")
    if tg is None or tg == "":
        target_cm: Optional[float] = None
    else:
        try:
            target_cm = float(tg)
        except (TypeError, ValueError):
            target_cm = None
    try:
        interval = int(h.get("interval") or 1440)
        if interval < 1:
            interval = 1440
    except (TypeError, ValueError):
        interval = 1440
    return {"target_cm": target_cm, "interval": interval}


def normalize_controls_for_api(d: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy so GET /api/control always exposes the current height shape."""
    out = dict(d)
    out["height"] = _sanitize_height_channel(out.get("height") or {})
    return out


def validate_merged_profile(data: Dict[str, Any]) -> None:
    """Raises ValueError on invalid user-visible ranges (same spirit as legacy Flask)."""
    temp = data.get("temperature") or {}
    tmin, tmax = temp.get("min"), temp.get("max")
    if tmin is not None and tmax is not None and float(tmin) >= float(tmax):
        raise ValueError("Invalid temperature range")
    twl = temp.get("warn_low")
    twh = temp.get("warn_high")
    if twh is None:
        twh = temp.get("warn")
    if twl is not None and twh is not None:
        try:
            if float(twl) >= float(twh):
                raise ValueError("Temperature tolerance low must be less than tolerance high")
        except (TypeError, ValueError):
            pass
    hum = data.get("humidity") or {}
    hmin, hmax = hum.get("min"), hum.get("max")
    if hmin is not None and hmax is not None and float(hmin) >= float(hmax):
        raise ValueError("Invalid humidity range (min must be less than max)")
    hwl = hum.get("warn_low")
    hwh = hum.get("warn_high")
    if hwh is None:
        hwh = hum.get("warn")
    if hwl is not None and hwh is not None:
        try:
            if float(hwl) >= float(hwh):
                raise ValueError("Humidity tolerance low must be less than tolerance high")
        except (TypeError, ValueError):
            pass
    for v in (hwh, hwl):
        if v is not None:
            try:
                fv = float(v)
            except (TypeError, ValueError):
                pass
            else:
                if fv > 100 or fv < 0:
                    raise ValueError("Humidity tolerance values must be between 0 and 100%")

    light = data.get("light") or {}
    lmin, lmax = light.get("min"), light.get("max")
    if lmin is not None and lmax is not None and float(lmin) >= float(lmax):
        raise ValueError("Invalid light range (min must be less than max)")
    lwl = light.get("warn_low")
    lw_hi = light.get("warn_high")
    if lw_hi is None:
        lw_hi = light.get("warn")
    if lwl is not None and lw_hi is not None:
        try:
            if float(lwl) >= float(lw_hi):
                raise ValueError("Light tolerance low must be less than tolerance high")
        except (TypeError, ValueError):
            pass

    motion = data.get("motion") or {}
    mmin, mmax = motion.get("min"), motion.get("max")
    if mmin is not None and mmax is not None and float(mmin) >= float(mmax):
        raise ValueError("Invalid motion range (min must be less than max)")
    mwl, mwh = motion.get("warn_low"), motion.get("warn")
    if mwl is not None and mwh is not None:
        try:
            wl, wh = float(mwl), float(mwh)
        except (TypeError, ValueError):
            pass
        else:
            if wl >= wh:
                raise ValueError("Motion tolerance low must be less than tolerance high")
            if wl < 0 or wh > 1:
                raise ValueError("Motion soft tolerances must be between 0 and 1 (PIR maps to 0/1)")
    height = data.get("height") or {}
    tg = height.get("target_cm")
    if tg is not None:
        try:
            if float(tg) <= 0:
                raise ValueError("Desired height must be a positive number (cm)")
        except (TypeError, ValueError) as ex:
            if isinstance(ex, ValueError) and "Desired height" in str(ex):
                raise
