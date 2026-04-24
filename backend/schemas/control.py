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
    return out


def validate_merged_profile(data: Dict[str, Any]) -> None:
    """Raises ValueError on invalid user-visible ranges (same spirit as legacy Flask)."""
    temp = data.get("temperature") or {}
    tmin, tmax = temp.get("min"), temp.get("max")
    if tmin is not None and tmax is not None and float(tmin) >= float(tmax):
        raise ValueError("Invalid temperature range")
    twl, twh = temp.get("warn_low"), temp.get("warn")
    if twl is not None and twh is not None:
        try:
            if float(twl) >= float(twh):
                raise ValueError("Temperature tolerance low must be less than tolerance high")
        except (TypeError, ValueError):
            pass
    hum = data.get("humidity") or {}
    hw = hum.get("warn")
    if hw is not None and float(hw) > 100:
        raise ValueError("Humidity tolerance cannot exceed 100%")
