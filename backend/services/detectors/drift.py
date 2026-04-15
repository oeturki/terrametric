"""
Drift Detector -- detects gradual sensor calibration loss.

Uses linear regression (least-squares) on a sliding window of readings.
If the slope exceeds the sensor's threshold, something is drifting.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from enums import AnomalyType, AlertSeverity
from .base import BaseDetector, AnomalyEvent, SensorProfile, Reading
from .rolling_buffer import RollingBuffer


class DriftDetector(BaseDetector):
    """
    Detects gradual sensor calibration loss using linear regression.

    HOW IT WORKS:
    Takes the last N readings (the "window") and fits a straight line through them
    using least-squares regression (numpy.polyfit).  The slope of that line tells us
    how fast the sensor value is changing per reading.

    If |slope| > the sensor's drift_slope_threshold, something is wrong -- the sensor
    is slowly drifting away from its true value.

    MATH:
        slope = (N * Sigma(x*y) - Sigma(x) * Sigma(y)) / (N * Sigma(x^2) - (Sigma(x))^2)
        where x = reading index [0, 1, 2, ...], y = sensor value

    SEVERITY:
        WARNING  if slope is 1-2x the threshold
        CRITICAL if slope exceeds 2x the threshold
    """

    def __init__(self, profiles: dict[str, SensorProfile], window_size: int):
        self._profiles = profiles
        self._window_size = window_size  # how many readings to fit the line through

    def detect_reading(
        self,
        reading: Reading,
        buffer: object,
        session_id: int,
    ) -> list[AnomalyEvent]:
        """
        Check all monitored variables in the buffer for drift.
        Called by the orchestrator once per reading, after the reading
        has been added to the buffer.
        """
        events = []
        if not isinstance(buffer, RollingBuffer):
            return events

        for variable, profile in self._profiles.items():
            event = self._detect_variable(buffer, variable, session_id, profile)
            if event:
                events.append(event)
        return events

    def detect(
        self,
        buffer: RollingBuffer,
        variable: str,
        session_id: int,
    ) -> Optional[AnomalyEvent]:
        """Public single-variable detection. Useful for unit tests and direct calls."""
        return self._detect_variable(buffer, variable, session_id, self._profiles[variable])

    def _detect_variable(
        self,
        buffer: RollingBuffer,
        variable: str,
        session_id: int,
        profile: SensorProfile,
    ) -> Optional[AnomalyEvent]:
        """Run drift detection on one variable."""
        # Need a full window before we can detect anything
        if buffer.size(variable) < self._window_size:
            return None

        # Grab the most recent window_size values
        values = buffer.get_values(variable)[-self._window_size:]

        # x-axis = [0, 1, 2, ..., N-1], y-axis = sensor readings
        x = np.arange(len(values), dtype=float)

        # polyfit returns [slope, intercept] for a degree-1 polynomial
        slope, _ = np.polyfit(x, values, 1)
        abs_slope = abs(slope)

        # Slope is within normal range -- no drift
        if abs_slope <= profile.drift_slope_threshold:
            return None

        # How many times over the threshold (used for severity)
        ratio = abs_slope / profile.drift_slope_threshold
        severity = AlertSeverity.CRITICAL if ratio > 2.0 else AlertSeverity.WARNING
        direction = "increasing" if slope > 0 else "decreasing"
        timestamps = buffer.get_timestamps(variable)

        return AnomalyEvent(
            timestamp=timestamps[-1],
            session_id=session_id,
            variable=variable,
            anomaly_type=AnomalyType.DRIFT,
            severity=severity,
            message=(
                f"{variable} drifting {direction} at {abs_slope:.4f} {profile.unit}/reading "
                f"(threshold: {profile.drift_slope_threshold})"
            ),
            detail={
                "slope": round(float(slope), 6),
                "threshold": profile.drift_slope_threshold,
                "window_size": self._window_size,
                "ratio": round(ratio, 2),
            },
        )
