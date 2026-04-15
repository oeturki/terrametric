"""
EWMA Detector -- Exponentially Weighted Moving Average control chart.

Industry-standard (ISO 7870-6) real-time monitoring technique that is more
sensitive to small sustained shifts than simple rolling window approaches.
Weighs recent readings more heavily than older ones.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from enums import AnomalyType, AlertSeverity
from .base import BaseDetector, AnomalyEvent, SensorProfile, Reading
from .rolling_buffer import RollingBuffer


class EWMADetector(BaseDetector):
    """
    Detects when a sensor value drifts outside EWMA control limits.

    MATH:
        ewma_t = lambda * x_t + (1 - lambda) * ewma_(t-1)

        Control limits (exact for i-th observation):
        UCL = mu_0 + L * sigma * sqrt( (lam/(2-lam)) * (1 - (1-lam)^(2*i)) )
        LCL = mu_0 - L * sigma * sqrt( (lam/(2-lam)) * (1 - (1-lam)^(2*i)) )

    Where:
        lambda (lam) = smoothing factor, typically 0.2
        L = width multiplier for control limits (like k in k-sigma), typically 3.0
        mu_0 = process mean (estimated from rolling buffer)
        sigma = process std dev (estimated from rolling buffer)

    For steady state (large i), the sqrt term converges to sqrt(lam/(2-lam)).
    """

    def __init__(
        self,
        profiles: dict[str, SensorProfile],
        lam: float = 0.2,
        L: float = 3.0,
        min_readings: int = 10,
        cooldown: int = 3,
    ):
        self._profiles = profiles
        self._lam = lam
        self._L = L
        self._min_readings = min_readings
        self._cooldown = cooldown
        self._ewma: dict[str, dict[str, float]] = {}
        self._count: dict[str, dict[str, int]] = {}
        self._since_alert: dict[str, dict[str, int]] = {}

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
        if key not in self._ewma:
            self._ewma[key] = {}
            self._count[key] = {}
            self._since_alert[key] = {}

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

            event = self._check_ewma(buffer, variable, float(value), session_id, key, profile, reading.timestamp)
            if event:
                events.append(event)

        return events

    def _check_ewma(self, buffer, variable, value, session_id, key, profile, timestamp):
        self._since_alert[key][variable] = self._since_alert[key].get(variable, self._cooldown) + 1

        values = buffer.get_values(variable)
        mu = float(np.mean(values))
        sigma = float(np.std(values))
        if sigma < 1e-9:
            return None

        prev_ewma = self._ewma[key].get(variable, mu)
        count = self._count[key].get(variable, 0) + 1
        self._count[key][variable] = count

        ewma_val = self._lam * value + (1 - self._lam) * prev_ewma
        self._ewma[key][variable] = ewma_val

        factor = np.sqrt((self._lam / (2 - self._lam)) * (1 - (1 - self._lam) ** (2 * count)))
        ucl = mu + self._L * sigma * factor
        lcl = mu - self._L * sigma * factor

        if lcl <= ewma_val <= ucl:
            return None

        if self._since_alert[key].get(variable, self._cooldown) < self._cooldown:
            return None

        self._since_alert[key][variable] = 0

        deviation = (ewma_val - mu) / sigma
        severity = AlertSeverity.CRITICAL if abs(deviation) > self._L * 1.3 else AlertSeverity.WARNING
        direction = "above" if ewma_val > ucl else "below"

        return AnomalyEvent(
            timestamp=timestamp,
            session_id=session_id,
            variable=variable,
            anomaly_type=AnomalyType.EWMA_BREACH,
            severity=severity,
            message=(
                f"{variable} EWMA breach ({direction}): "
                f"EWMA={ewma_val:.2f}, limits=[{lcl:.2f}, {ucl:.2f}] {profile.unit}"
            ),
            detail={
                "ewma": round(ewma_val, 4),
                "ucl": round(ucl, 4),
                "lcl": round(lcl, 4),
                "mean": round(mu, 4),
                "sigma": round(sigma, 4),
                "deviation_sigma": round(deviation, 2),
                "lambda": self._lam,
                "L": self._L,
            },
        )

    def reset(self, session_id: int) -> None:
        key = str(session_id)
        self._ewma.pop(key, None)
        self._count.pop(key, None)
        self._since_alert.pop(key, None)
