"""
Light residual cumulative-sum detector (optional core tier).

CUSUM-lite on standardized residuals vs a prior-window median baseline. Emits LEVEL_SHIFT:
useful when single points are modest but evidence accumulates. Distinct hypothesis from Spike
(z-score on one reading).

Omitted when ``extended_detectors`` is True to avoid stacking next to ``CUSUMDetector`` in the lab.
"""

from __future__ import annotations

import numpy as np

from enums import AnomalyType, AlertSeverity
from .base import BaseDetector, AnomalyEvent, SensorProfile, Reading
from .rolling_buffer import RollingBuffer


class LightResidualCUSUMDetector(BaseDetector):
    def __init__(
        self,
        profiles: dict[str, SensorProfile],
        *,
        allowance_k: float = 0.35,
        decision_h: float = 4.0,
        baseline_window: int = 15,
        min_prior: int = 8,
    ):
        self._profiles = profiles
        self._k = allowance_k
        self._h = decision_h
        self._baseline_window = max(3, baseline_window)
        self._min_prior = max(3, min_prior)
        self._state: dict[str, dict[str, dict[str, float]]] = {}

    def reset(self, session_id: int) -> None:
        self._state.pop(str(session_id), None)

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
        if key not in self._state:
            self._state[key] = {v: {"hi": 0.0, "lo": 0.0} for v in self._profiles}

        variable_values = {
            "temperature": reading.temperature,
            "humidity": reading.humidity,
            "light": reading.light,
        }

        for variable, profile in self._profiles.items():
            value = variable_values.get(variable)
            if value is None:
                continue
            vals = buffer.get_values(variable)
            if len(vals) < self._min_prior + 1:
                continue
            priors = vals[-(self._baseline_window + 1) : -1]
            if len(priors) < self._min_prior:
                continue

            baseline = float(np.median(priors))
            r = float(value) - baseline
            denom = max(profile.baseline_noise, 1e-9)
            z = r / denom

            s = self._state[key][variable]
            s_hi = max(0.0, s["hi"] + (z - self._k))
            s_lo = max(0.0, s["lo"] + (-z - self._k))
            s["hi"] = s_hi
            s["lo"] = s_lo

            if s_hi > self._h:
                s["hi"] = 0.0
                direction = "upward_residual"
                cusum_v = s_hi
            elif s_lo > self._h:
                s["lo"] = 0.0
                direction = "downward_residual"
                cusum_v = s_lo
            else:
                continue

            severity = AlertSeverity.CRITICAL if cusum_v > self._h * 1.5 else AlertSeverity.WARNING

            events.append(
                AnomalyEvent(
                    timestamp=reading.timestamp,
                    session_id=session_id,
                    variable=variable,
                    anomaly_type=AnomalyType.LEVEL_SHIFT,
                    severity=severity,
                    message=(
                        f"{variable} sustained residual shift ({direction}): reading {value:.1f} vs "
                        f"prior median {baseline:.1f} {profile.unit} (CUSUM={cusum_v:.2f})"
                    ),
                    detail={
                        "direction": direction,
                        "value": round(float(value), 3),
                        "baseline_median": round(baseline, 3),
                        "residual": round(r, 4),
                        "cusum": round(cusum_v, 3),
                        "threshold_h": self._h,
                        "allowance_k": self._k,
                        "reason": "core_light_residual_cusum",
                    },
                )
            )

        return events
