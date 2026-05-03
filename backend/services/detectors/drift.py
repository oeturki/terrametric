"""
Drift Detector -- detects gradual sensor calibration loss.

OLS slope on a sliding window; when enough history exists, the window excludes the
current point so a single aberrant reading does not dominate the slope.
Optional R² veto screens wobbly (poor-fit) segments; optional Kendall-tau suppression
gates non-monotonic windows (Mann–Kendall-style trend screening).
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from enums import AnomalyType, AlertSeverity
from .base import BaseDetector, AnomalyEvent, SensorProfile, Reading
from .rolling_buffer import RollingBuffer


class DriftDetector(BaseDetector):
    """
    Least-squares slope on ``window_size`` readings (prior-only when possible).

    Severity: WARNING if ratio in (1, 2]; CRITICAL if ratio > 2.
    """

    def __init__(
        self,
        profiles: dict[str, SensorProfile],
        window_size: int,
        *,
        min_r_squared: float = 0.0,
        use_mk_suppression: bool = False,
        mk_p_max: float = 0.15,
    ):
        self._profiles = profiles
        self._window_size = window_size
        self._min_r_squared = min_r_squared
        self._use_mk_suppression = use_mk_suppression
        self._mk_p_max = mk_p_max

    def detect_reading(
        self,
        reading: Reading,
        buffer: object,
        session_id: int,
    ) -> list[AnomalyEvent]:
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
        return self._detect_variable(buffer, variable, session_id, self._profiles[variable])

    def _window_values(self, buffer: RollingBuffer, variable: str) -> Optional[np.ndarray]:
        all_v = buffer.get_values(variable)
        if len(all_v) < self._window_size:
            return None
        if len(all_v) >= self._window_size + 1:
            return np.asarray(all_v[-(self._window_size + 1) : -1], dtype=float)
        return np.asarray(all_v[-self._window_size :], dtype=float)

    def _detect_variable(
        self,
        buffer: RollingBuffer,
        variable: str,
        session_id: int,
        profile: SensorProfile,
    ) -> Optional[AnomalyEvent]:
        values = self._window_values(buffer, variable)
        if values is None or values.size < 2:
            return None

        x = np.arange(len(values), dtype=float)
        slope, intercept = np.polyfit(x, values, 1)

        mean_y = float(np.mean(values))
        ss_tot = float(np.sum((values - mean_y) ** 2))
        residuals = values - (slope * x + intercept)
        ss_res = float(np.sum(residuals ** 2))
        r_squared = float("nan") if ss_tot <= 1e-18 else 1.0 - ss_res / ss_tot

        if not np.isnan(r_squared) and r_squared < self._min_r_squared:
            return None

        abs_slope = abs(float(slope))
        if abs_slope <= profile.drift_slope_threshold:
            return None

        if self._use_mk_suppression:
            from scipy.stats import kendalltau

            tau, pvalue = kendalltau(np.arange(len(values), dtype=float), values)
            pvalue_f = float(pvalue) if pvalue is not None and not np.isnan(pvalue) else 1.0
            if pvalue_f > self._mk_p_max:
                return None

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
                "window_size": int(values.size),
                "ratio": round(ratio, 2),
                "r_squared": round(r_squared, 4) if not np.isnan(r_squared) else None,
                "prior_only": buffer.size(variable) >= self._window_size + 1,
            },
        )
