"""
Default control profile per new plant. Single source of truth for the backend.
Matches the legacy Flask default_controls in backend/control.py and frontend fallbacks.
"""

from __future__ import annotations

import copy
import json
from typing import Any, Dict

DEFAULT_CONTROL_DICT: Dict[str, Any] = {
    "temperature": {"min": 15, "max": 30, "warn_low": None, "warn": 28, "interval": 60},
    "humidity": {"min": 20, "max": 40, "warn_low": None, "warn": 5, "interval": 60},
    "light": {"min": 5000, "max": 10000, "warn_low": None, "warn": 500, "interval": 60},
    "motion": {"min": 0, "max": 1, "warn_low": None, "warn": 1, "interval": 20},
    # Single optional goal height (cm). No min/max/tolerance for height — milestone capture fires once per recording session when reached.
    "height": {"target_cm": None, "interval": 1440},
    # Desired min/max breaches always snapshot while Pi camera is configured (like height milestones).
    # on_alert = also snapshot on temp/humidity/light tolerance (soft warn) breach.
    # on_motion = PI low→high edge snapshot (default on; set False to suppress noise).
    "camera": {"on_motion": True, "on_alert": True, "interval": 60},
}


def default_control_json() -> str:
    return json.dumps(default_control_dict())


def default_control_dict() -> Dict[str, Any]:
    return copy.deepcopy(DEFAULT_CONTROL_DICT)
