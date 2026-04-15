"""
CUSUM Detector -- cumulative sum change-point detection.

Catches sudden permanent level shifts (e.g. someone opens a greenhouse door,
temperature drops 5C and stays there).  Much faster than drift detection
for abrupt changes because it accumulates evidence over time.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from enums import AnomalyType, AlertSeverity
from .base import BaseDetector, AnomalyEvent, SensorProfile, Reading
from .rolling_buffer import RollingBuffer


CUSUM_PARAMS: dict[str, dict] = {
    "temperature": {"k": 0.5, "h": 4.0},
    "humidity":    {"k": 2.0, "h": 8.0},
    "light":       {"k": 15.0, "h": 60.0},
}


class CUSUMDetector(BaseDetector):
    """
    Tabular CUSUM (Page's test) for detecting shifts in the process mean.

    MATH:
        S_high(t) = max(0, S_high(t-1) + (x_t - mean - k))
        S_low(t)  = max(0, S_low(t-1)  + (mean - x_t - k))

        If S_high > h: upward shift detected
        If S_low  > h: downward shift detected

    Where k is the allowance (slack) and h is the decision threshold.
    After detection, the CUSUM is reset so it doesn't re-trigger on the
    same shift.

    The running mean is estimated from the rolling buffer.
    """

    def __init__(
        self,
        profiles: dict[str, SensorProfile],
        min_readings: int = 10,
    ):
        self._profiles = profiles
        self._min_readings = min_readings
        self._s_high: dict[str, dict[str, float]] = {}
        self._s_low: dict[str, dict[str, float]] = {}

    def detect_reading(
        self,
        reading: Reading,
        buffer: object,
        session_id: int,
    ) -> list[AnomalyEvent]:
        events = []
        if not isinstance(buffer, RollingBuffer):
            return events

        key = str(session_id)
        if key not in self._s_high:
            self._s_high[key] = {}
            self._s_low[key] = {}

        variable_values = {
            "temperature": reading.temperature,
            "humidity": reading.humidity,
            "light": reading.light,
        }

        for variable, profile in self._profiles.items():
            value = variable_values.get(variable)
            if value is None:
                continue
            if buffer.size(variable) < self._min_readings:
                continue

            event = self._check_cusum(buffer, variable, float(value), session_id, key, profile, reading.timestamp)
            if event:
                events.append(event)

        return events

    def _check_cusum(self, buffer, variable, value, session_id, key, profile, timestamp):
        params = CUSUM_PARAMS.get(variable, {"k": 1.0, "h": 5.0})
        k = params["k"]
        h = params["h"]

        values = buffer.get_values(variable)
        mean = float(np.mean(values))

        s_h = self._s_high[key].get(variable, 0.0)
        s_l = self._s_low[key].get(variable, 0.0)

        s_h = max(0.0, s_h + (value - mean - k))
        s_l = max(0.0, s_l + (mean - value - k))

        self._s_high[key][variable] = s_h
        self._s_low[key][variable] = s_l

        if s_h > h:
            self._s_high[key][variable] = 0.0
            direction = "upward"
            cusum_val = s_h
        elif s_l > h:
            self._s_low[key][variable] = 0.0
            direction = "downward"
            cusum_val = s_l
        else:
            return None

        shift_magnitude = abs(value - mean)

        severity = AlertSeverity.CRITICAL if cusum_val > h * 1.5 else AlertSeverity.WARNING

        return AnomalyEvent(
            timestamp=timestamp,
            session_id=session_id,
            variable=variable,
            anomaly_type=AnomalyType.LEVEL_SHIFT,
            severity=severity,
            message=(
                f"{variable} level shift ({direction}): "
                f"value {value:.1f} vs mean {mean:.1f} {profile.unit} "
                f"(CUSUM={cusum_val:.1f}, threshold={h})"
            ),
            detail={
                "direction": direction,
                "value": round(value, 2),
                "mean": round(mean, 2),
                "cusum": round(cusum_val, 2),
                "threshold_h": h,
                "allowance_k": k,
                "shift_magnitude": round(shift_magnitude, 2),
            },
        )

    def reset(self, session_id: int) -> None:
        key = str(session_id)
        self._s_high.pop(key, None)
        self._s_low.pop(key, None)
