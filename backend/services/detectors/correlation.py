"""
Correlation Detector -- detects when physically correlated sensors diverge.

Temperature and humidity from the DHT11 are physically linked (warmer air
holds more moisture).  When this correlation breaks, it usually means one
sensor is faulty.  Per-variable detectors can't catch this.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from enums import AnomalyType, AlertSeverity
from .base import BaseDetector, AnomalyEvent, Reading
from .rolling_buffer import RollingBuffer


class CorrelationDetector(BaseDetector):
    """
    Tracks the rolling Pearson correlation between temperature and humidity.

    MATH:
        r = cov(X, Y) / (std(X) * std(Y))
        r ranges from -1 (perfect negative) to +1 (perfect positive)

    For the DHT11 in a greenhouse, |r| is typically 0.5-0.9.  When it drops
    below the warning threshold, the sensors are no longer agreeing.

    SEVERITY:
        WARNING  when |r| < warning_threshold (default 0.3)
        CRITICAL when |r| < critical_threshold (default 0.1)
    """

    def __init__(
        self,
        window_size: int = 15,
        warning_threshold: float = 0.3,
        critical_threshold: float = 0.1,
        cooldown: int = 5,
    ):
        self._window_size = window_size
        self._warning_threshold = warning_threshold
        self._critical_threshold = critical_threshold
        self._cooldown = cooldown
        self._readings_since_alert: dict[int, int] = {}

    def detect_reading(
        self,
        reading: Reading,
        buffer: object,
        session_id: int,
    ) -> list[AnomalyEvent]:
        if not isinstance(buffer, RollingBuffer):
            return []

        if session_id not in self._readings_since_alert:
            self._readings_since_alert[session_id] = self._cooldown

        self._readings_since_alert[session_id] += 1

        if buffer.size("temperature") < self._window_size or buffer.size("humidity") < self._window_size:
            return []

        if self._readings_since_alert[session_id] < self._cooldown:
            return []

        temp_vals = buffer.get_values("temperature")[-self._window_size:]
        hum_vals = buffer.get_values("humidity")[-self._window_size:]

        if len(temp_vals) != len(hum_vals):
            return []

        temp_std = float(np.std(temp_vals))
        hum_std = float(np.std(hum_vals))
        if temp_std < 1e-9 or hum_std < 1e-9:
            return []

        r = float(np.corrcoef(temp_vals, hum_vals)[0, 1])
        abs_r = abs(r)

        if abs_r >= self._warning_threshold:
            return []

        severity = AlertSeverity.CRITICAL if abs_r < self._critical_threshold else AlertSeverity.WARNING
        self._readings_since_alert[session_id] = 0

        timestamps = buffer.get_timestamps("temperature")

        return [AnomalyEvent(
            timestamp=timestamps[-1],
            session_id=session_id,
            variable="temperature+humidity",
            anomaly_type=AnomalyType.CORRELATION,
            severity=severity,
            message=f"Temp-humidity correlation broken: r={r:.3f} (threshold: {self._warning_threshold})",
            detail={
                "pearson_r": round(r, 4),
                "abs_r": round(abs_r, 4),
                "warning_threshold": self._warning_threshold,
                "critical_threshold": self._critical_threshold,
                "window_size": self._window_size,
            },
        )]

    def reset(self, session_id: int) -> None:
        self._readings_since_alert.pop(session_id, None)
