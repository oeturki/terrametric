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
    "humidity": {"min": 20, "max": 40, "warn": 5, "interval": 60},
    "light": {"min": 5000, "max": 10000, "warn": 500, "interval": 60},
    "motion": {"min": 0, "max": 1, "warn": 1, "interval": 20},
    "height": {"min": 0, "max": 10000, "warn": 5, "interval": 1440},
    "camera": {"on_motion": False, "on_alert": False, "interval": 60},
}


def default_control_json() -> str:
    return json.dumps(default_control_dict())


def default_control_dict() -> Dict[str, Any]:
    return copy.deepcopy(DEFAULT_CONTROL_DICT)
