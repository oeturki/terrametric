"""
Seasonal Detector -- time-of-day aware baseline for the light sensor.

Light naturally follows a daily cycle (bright during day, dark at night).
Without this detector, the standard drift/noise detectors would flag the
sunset dip or sunrise spike as anomalies.  This detector builds a per-hour
baseline and only flags deviations from the *expected value for that hour*.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Optional

import numpy as np

from enums import AnomalyType, AlertSeverity
from .base import BaseDetector, AnomalyEvent, SensorProfile, Reading
from .rolling_buffer import RollingBuffer


class SeasonalDetector(BaseDetector):
    """
    Builds a per-hour-of-day baseline for the light sensor, then flags
    readings that deviate from the expected value for that specific hour.

    LEARNING PHASE:
        Collects light readings bucketed by hour (0-23).  Once we have at
        least min_per_hour readings for min_hours distinct hours, the
        baseline is established.

    DETECTION PHASE:
        For each light reading, look up the baseline mean and std for the
        current hour.  If the reading deviates by more than threshold_sigma
        standard deviations, flag it.

    Only applies to the light variable.
    """

    def __init__(
        self,
        threshold_sigma: float = 3.0,
        critical_sigma: float = 5.0,
        min_per_hour: int = 3,
        min_hours: int = 4,
    ):
        self._threshold_sigma = threshold_sigma
        self._critical_sigma = critical_sigma
        self._min_per_hour = min_per_hour
        self._min_hours = min_hours
        self._hourly_data: dict[int, defaultdict] = {}
        self._baselines: dict[int, dict[int, tuple[float, float]]] = {}

    def detect_reading(
        self,
        reading: Reading,
        buffer: object,
        session_id: int,
    ) -> list[AnomalyEvent]:
        if reading.light is None:
            return []

        value = float(reading.light)
        hour = reading.timestamp.hour

        if session_id not in self._hourly_data:
            self._hourly_data[session_id] = defaultdict(list)

        self._hourly_data[session_id][hour].append(value)

        if session_id not in self._baselines:
            hourly = self._hourly_data[session_id]
            qualified_hours = sum(
                1 for h_vals in hourly.values()
                if len(h_vals) >= self._min_per_hour
            )
            if qualified_hours >= self._min_hours:
                baseline = {}
                for h, vals in hourly.items():
                    if len(vals) >= self._min_per_hour:
                        baseline[h] = (float(np.mean(vals)), max(float(np.std(vals)), 1.0))
                self._baselines[session_id] = baseline
            return []

        baseline = self._baselines[session_id]
        if hour not in baseline:
            return []

        expected_mean, expected_std = baseline[hour]
        deviation = abs(value - expected_mean) / expected_std

        if deviation <= self._threshold_sigma:
            return []

        severity = AlertSeverity.CRITICAL if deviation > self._critical_sigma else AlertSeverity.WARNING
        direction = "above" if value > expected_mean else "below"

        return [AnomalyEvent(
            timestamp=reading.timestamp,
            session_id=session_id,
            variable="light",
            anomaly_type=AnomalyType.SEASONAL,
            severity=severity,
            message=(
                f"Light unusual for hour {hour:02d}:00: {value:.0f} "
                f"({deviation:.1f}σ {direction} expected {expected_mean:.0f})"
            ),
            detail={
                "value": round(value, 1),
                "hour": hour,
                "expected_mean": round(expected_mean, 1),
                "expected_std": round(expected_std, 1),
                "deviation_sigma": round(deviation, 2),
            },
        )]

    def reset(self, session_id: int) -> None:
        self._hourly_data.pop(session_id, None)
        self._baselines.pop(session_id, None)
