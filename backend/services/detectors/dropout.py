"""
Dropout Detector -- detects gaps / missing data in the reading stream.

Learns the expected interval dynamically from the first N readings,
then flags gaps that exceed a configurable multiplier of that baseline.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import numpy as np

from enums import AnomalyType, AlertSeverity
from .base import BaseDetector, AnomalyEvent, Reading
from .rolling_buffer import RollingBuffer


class DropoutDetector(BaseDetector):
    """
    Detects gaps / missing data in the reading stream.

    HOW IT WORKS:
    Compares the time between consecutive readings against an "expected interval"
    that is learned dynamically from the first N readings (not hardcoded).

    LEARNING PHASE (first N readings):
    We collect the time gaps between each pair of consecutive readings.  Once we
    have N gaps, we take the median as the expected interval.  Median is used
    instead of mean so a single outlier during startup doesn't corrupt the baseline.

    DETECTION PHASE (after baseline is set):
    If the gap between two readings exceeds `multiplier * expected_interval`,
    we flag it as a dropout.

    SEVERITY:
        Assigns INFO / WARNING / CRITICAL via ``severity_warning_ratio`` and
        ``severity_critical_ratio`` (defaults align with legacy 5× and 15× gap ratios vs expected).

    STATE:
    Tracked per session_id so multiple simultaneous sessions don't interfere.
    """

    def __init__(
        self,
        multiplier: int,
        baseline_count: int,
        severity_warning_ratio: int = 5,
        severity_critical_ratio: int = 15,
    ):
        self._multiplier = multiplier          # gap must exceed this many x expected to trigger
        self._baseline_count = baseline_count  # how many intervals to collect before detecting
        self._warn_ratio = severity_warning_ratio
        self._crit_ratio = severity_critical_ratio
        # Per-session state:
        self._last_seen: dict[int, datetime] = {}       # timestamp of most recent reading
        self._intervals: dict[int, list[float]] = {}    # collected gaps during learning phase
        self._baselines: dict[int, float] = {}          # computed expected interval (seconds)

    def detect_reading(
        self,
        reading: Reading,
        buffer: object,
        session_id: int,
    ) -> list[AnomalyEvent]:
        """
        Check for a data gap based on the reading's timestamp.
        The buffer parameter is unused by this detector (gaps are purely
        timestamp-based), but it's part of the BaseDetector interface.
        """
        event = self._detect_gap(session_id, reading.timestamp)
        return [event] if event else []

    def detect(self, session_id: int, timestamp: datetime) -> Optional[AnomalyEvent]:
        """Public convenience method. Useful for unit tests and direct calls."""
        return self._detect_gap(session_id, timestamp)

    def _detect_gap(self, session_id: int, timestamp: datetime) -> Optional[AnomalyEvent]:
        """Core gap detection logic."""
        # Very first reading for this session -- just record the timestamp, nothing to compare
        if session_id not in self._last_seen:
            self._last_seen[session_id] = timestamp
            self._intervals[session_id] = []
            return None

        # Calculate how many seconds since the last reading
        gap = (timestamp - self._last_seen[session_id]).total_seconds()
        self._last_seen[session_id] = timestamp

        # LEARNING PHASE: still collecting intervals to establish the baseline
        if session_id not in self._baselines:
            self._intervals[session_id].append(gap)
            # Once we have enough samples, compute the baseline
            if len(self._intervals[session_id]) >= self._baseline_count:
                self._baselines[session_id] = float(
                    np.median(self._intervals[session_id])
                )
            return None  # never flag during learning phase

        # DETECTION PHASE: compare this gap against baseline
        expected = self._baselines[session_id]
        if expected <= 0:
            return None

        # How many times larger is this gap than expected?
        gap_ratio = gap / expected
        if gap_ratio <= self._multiplier:
            return None  # gap is within acceptable range

        # Estimate how many readings were missed in this gap
        missed = int(gap / expected) - 1

        # Assign severity based on how extreme the gap is (align with SAMPLING_INTERVAL / Pi cadence via env).
        if gap_ratio > self._crit_ratio:
            severity = AlertSeverity.CRITICAL
        elif gap_ratio > self._warn_ratio:
            severity = AlertSeverity.WARNING
        else:
            severity = AlertSeverity.INFO

        return AnomalyEvent(
            timestamp=timestamp,
            session_id=session_id,
            variable="all",  # dropout affects all variables equally
            anomaly_type=AnomalyType.DROPOUT,
            severity=severity,
            message=(
                f"Data gap detected: {gap:.1f}s ({missed} readings missed, "
                f"expected interval: {expected:.1f}s)"
            ),
            detail={
                "gap_seconds": round(gap, 2),
                "expected_interval": round(expected, 2),
                "missed_readings": missed,
                "gap_ratio": round(gap_ratio, 1),
            },
        )

    def reset(self, session_id: int) -> None:
        """Wipe all state for a session (called when session ends)."""
        self._last_seen.pop(session_id, None)
        self._intervals.pop(session_id, None)
        self._baselines.pop(session_id, None)
