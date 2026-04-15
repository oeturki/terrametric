"""
Spike Detector -- catches single readings that are wildly out of range.

Two layers of protection:
  1. Hard bounds: reject physically impossible values (DHT11 returning 0/255)
  2. Statistical: flag values more than k standard deviations from the rolling mean
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from enums import AnomalyType, AlertSeverity
from .base import BaseDetector, AnomalyEvent, SensorProfile, Reading
from .rolling_buffer import RollingBuffer


HARD_BOUNDS: dict[str, tuple[float, float]] = {
    "temperature": (-10.0, 60.0),
    "humidity": (0.0, 100.0),
    "light": (0.0, 1023.0),
}

MIN_BUFFER_SIZE = 5


class SpikeDetector(BaseDetector):
    """
    Detects single-reading outliers using z-score and hard range bounds.

    Unlike the NoiseDetector (which looks at the window's overall jitter),
    SpikeDetector fires on *individual* readings that deviate sharply from
    the recent trend.  This catches DHT11 glitches that return 0 or 255
    for a single cycle before recovering.

    MATH:
        z = |x - mean| / std
        WARNING  at z > warning_z  (default 4.0)
        CRITICAL at z > critical_z (default 6.0)

    Hard bounds are checked first -- any reading outside the physical range
    of the sensor is automatically CRITICAL regardless of z-score.
    """

    def __init__(
        self,
        profiles: dict[str, SensorProfile],
        warning_z: float = 4.0,
        critical_z: float = 6.0,
    ):
        self._profiles = profiles
        self._warning_z = warning_z
        self._critical_z = critical_z

    def detect_reading(
        self,
        reading: Reading,
        buffer: object,
        session_id: int,
    ) -> list[AnomalyEvent]:
        events = []
        if not isinstance(buffer, RollingBuffer):
            return events

        variable_values = {
            "temperature": reading.temperature,
            "humidity": reading.humidity,
            "light": reading.light,
        }

        for variable, profile in self._profiles.items():
            value = variable_values.get(variable)
            if value is None:
                continue
            event = self._check_spike(buffer, variable, float(value), session_id, profile, reading.timestamp)
            if event:
                events.append(event)
        return events

    def _check_spike(self, buffer, variable, value, session_id, profile, timestamp):
        lo, hi = HARD_BOUNDS.get(variable, (float("-inf"), float("inf")))
        if value < lo or value > hi:
            return AnomalyEvent(
                timestamp=timestamp,
                session_id=session_id,
                variable=variable,
                anomaly_type=AnomalyType.SPIKE,
                severity=AlertSeverity.CRITICAL,
                message=f"{variable} out of physical range: {value} {profile.unit} (bounds: {lo}-{hi})",
                detail={"value": value, "lower_bound": lo, "upper_bound": hi, "reason": "hard_bounds"},
            )

        if buffer.size(variable) < MIN_BUFFER_SIZE:
            return None

        values = buffer.get_values(variable)
        mean = float(np.mean(values))
        std = float(np.std(values))

        if std < 1e-9:
            if abs(value - mean) > profile.baseline_noise * self._warning_z:
                return AnomalyEvent(
                    timestamp=timestamp,
                    session_id=session_id,
                    variable=variable,
                    anomaly_type=AnomalyType.SPIKE,
                    severity=AlertSeverity.CRITICAL,
                    message=f"{variable} spike: {value:.1f} {profile.unit} (all prior readings identical at {mean:.1f})",
                    detail={"value": round(value, 2), "mean": round(mean, 2), "std": 0.0, "z_score": float("inf"), "reason": "zero_variance"},
                )
            return None

        z = abs(value - mean) / std
        if z <= self._warning_z:
            return None

        severity = AlertSeverity.CRITICAL if z > self._critical_z else AlertSeverity.WARNING
        direction = "above" if value > mean else "below"

        return AnomalyEvent(
            timestamp=timestamp,
            session_id=session_id,
            variable=variable,
            anomaly_type=AnomalyType.SPIKE,
            severity=severity,
            message=f"{variable} spike: {value:.1f} {profile.unit} ({z:.1f}σ {direction} mean of {mean:.1f})",
            detail={"value": round(value, 2), "mean": round(mean, 2), "std": round(std, 4), "z_score": round(z, 2)},
        )
