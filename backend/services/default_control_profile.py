"""
Default control profile per new plant. Single source of truth for the backend.
Comfort-oriented indoor-room baselines for desired bands and soft tolerance.
"""

from __future__ import annotations

import copy
import json
from typing import Any, Dict

DEFAULT_CONTROL_DICT: Dict[str, Any] = {
    "temperature": {"min": 18, "max": 26, "warn_low": 16, "warn_high": 28, "interval": 120},
    "humidity": {"min": 40, "max": 60, "warn_low": 35, "warn_high": 68, "interval": 120},
    "light": {"min": 200, "max": 2500, "warn_low": 120, "warn_high": 3200, "interval": 120},
    # Motion: read interval only; bounds are sanitized away (binary PIR).
    "motion": {"interval": 60},
    "height": {"target_cm": None, "interval": 1440},
    "camera": {"on_motion": True, "on_alert": True, "interval": 60},
}


def default_control_json() -> str:
    return json.dumps(default_control_dict())


def default_control_dict() -> Dict[str, Any]:
    return copy.deepcopy(DEFAULT_CONTROL_DICT)
