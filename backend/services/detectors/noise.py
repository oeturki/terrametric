"""
Noise Detector -- detects abnormally jittery sensor readings.

Uses rolling standard deviation compared against the sensor's known baseline.
Includes DHT11-specific deduplication of consecutive identical values.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from enums import AnomalyType, AlertSeverity
from .base import BaseDetector, AnomalyEvent, SensorProfile, Reading
from .rolling_buffer import RollingBuffer


class NoiseDetector(BaseDetector):
    """
    Detects abnormally jittery sensor readings using rolling standard deviation.

    HOW IT WORKS:
    Takes the last N readings, computes their standard deviation, and compares it
    against the sensor's known baseline noise.  If std dev is much larger than
    normal, the sensor is degrading or there's electrical interference.

    MATH:
        std = sqrt( (1/N) * Sigma(xi - mean)^2 )
        ratio = std / baseline_noise

    DEDUPLICATION:
    The DHT11 only updates every ~2s but the Arduino sends every 200ms, so many
    consecutive readings are identical copies.  These deflate the std dev
    artificially.  We strip consecutive duplicates before computing std.

    SEVERITY:
        WARNING  at warning_multiplier x baseline noise  (default 3x)
        CRITICAL at critical_multiplier x baseline noise (default 5x)
    """

    def __init__(
        self,
        profiles: dict[str, SensorProfile],
        window_size: int,
        warning_multiplier: float,     # e.g. 3.0 -- flag WARNING if noise is 3x baseline
        critical_multiplier: float,    # e.g. 5.0 -- flag CRITICAL if noise is 5x baseline
    ):
        self._profiles = profiles
        self._window_size = window_size
        self._warning_mult = warning_multiplier
        self._critical_mult = critical_multiplier

    def detect_reading(
        self,
        reading: Reading,
        buffer: object,
        session_id: int,
    ) -> list[AnomalyEvent]:
        """Check all monitored variables in the buffer for excessive noise."""
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
        """Run noise detection on one variable."""
        # Need a full window before we can detect anything
        if buffer.size(variable) < self._window_size:
            return None

        all_v = buffer.get_values(variable)
        if buffer.size(variable) >= self._window_size + 1:
            values = all_v[-(self._window_size + 1) : -1]
        else:
            values = all_v[-self._window_size :]

        # Strip consecutive duplicate values caused by DHT11's slow update rate.
        # e.g. [22, 22, 22, 23, 23, 22] becomes [22, 23, 22]
        deduped = [values[0]]
        for v in values[1:]:
            if v != deduped[-1]:
                deduped.append(v)

        # If almost all values are identical, there's no meaningful noise to measure
        if len(deduped) < 3:
            return None

        # Compute standard deviation of the unique readings
        std = float(np.std(deduped))

        # How many times noisier than the healthy baseline?
        ratio = std / profile.baseline_noise if profile.baseline_noise > 0 else 0.0

        # Noise is within acceptable range
        if ratio <= self._warning_mult:
            return None

        severity = (
            AlertSeverity.CRITICAL if ratio > self._critical_mult
            else AlertSeverity.WARNING
        )
        timestamps = buffer.get_timestamps(variable)

        return AnomalyEvent(
            timestamp=timestamps[-1],
            session_id=session_id,
            variable=variable,
            anomaly_type=AnomalyType.NOISE,
            severity=severity,
            message=(
                f"{variable} noise elevated: std={std:.2f} {profile.unit} "
                f"({ratio:.1f}x baseline of {profile.baseline_noise})"
            ),
            detail={
                "std_dev": round(std, 4),
                "baseline": profile.baseline_noise,
                "ratio": round(ratio, 2),
                "window_size": self._window_size,
                "unique_values_in_window": len(deduped),
                "prior_only": buffer.size(variable) >= self._window_size + 1,
            },
        )
