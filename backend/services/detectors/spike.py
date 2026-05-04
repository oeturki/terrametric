"""
Spike Detector -- catches single readings that are wildly out of range.

Two layers of protection:
  1. Hard bounds: reject physically impossible values (DHT11 returning 0/255)
  2. Statistical: flag values more than k effective-sigma from the rolling mean of *prior* readings
     (current point excluded from mean/scale to avoid self-influence).
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

# Secondary gate: abrupt step vs previous reading vs noise floor alone (covers diurnal ramps
# where rolling mean/variance absorbs the anomaly so classical z-vs-mean stays low).
STEP_SPIKE_ABS_MIN: dict[str, float] = {
    "temperature": 2.8,
    "humidity": 7.5,
    "light": 65.0,
}


class SpikeDetector(BaseDetector):
    """
    Single-reading outliers: z-style score vs prior window + hard bounds.

    Prior-only baseline avoids inflating/deflating spread with the candidate point.
    ``effective_std = max(raw_scale, baseline_noise / std_floor_denom)`` reduces
    false spikes on nearly flat traces; optional MAD via ``use_mad``.
    """

    def __init__(
        self,
        profiles: dict[str, SensorProfile],
        warning_z: float = 4.0,
        critical_z: float = 6.0,
        std_floor_denom: float = 4.0,
        min_prior: int = 5,
        min_abs_delta: float = 0.0,
        use_mad: bool = False,
    ):
        self._profiles = profiles
        self._warning_z = warning_z
        self._critical_z = critical_z
        self._std_floor_denom = max(std_floor_denom, 1e-6)
        self._min_prior = max(min_prior, 2)
        self._min_abs_delta = max(min_abs_delta, 0.0)
        self._use_mad = use_mad

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
            event = self._check_spike(
                buffer, variable, float(value), session_id, profile, reading.timestamp
            )
            if event:
                events.append(event)
        return events

    def _scale_and_mean(self, priors: np.ndarray, profile: SensorProfile) -> tuple[float, float]:
        mean = float(np.mean(priors))
        floor = profile.baseline_noise / self._std_floor_denom
        if self._use_mad:
            med = float(np.median(priors))
            mad = float(np.median(np.abs(priors - med)))
            mad_sigma = mad * 1.4826
            scale = max(mad_sigma, floor, 1e-9)
        else:
            std = float(np.std(priors, ddof=0))
            scale = max(std, floor, 1e-9)
        return mean, scale

    def _check_spike(
        self,
        buffer: RollingBuffer,
        variable: str,
        value: float,
        session_id: int,
        profile: SensorProfile,
        timestamp,
    ):
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

        if buffer.size(variable) < self._min_prior + 1:
            return None

        values = buffer.get_values(variable)
        priors = np.asarray(values[:-1], dtype=float)
        if priors.size < self._min_prior:
            return None

        mean, scale = self._scale_and_mean(priors, profile)

        z = abs(value - mean) / scale
        if self._min_abs_delta > 0 and abs(value - mean) < self._min_abs_delta:
            return None

        if z > self._warning_z:
            severity = AlertSeverity.CRITICAL if z > self._critical_z else AlertSeverity.WARNING
            direction = "above" if value > mean else "below"
            scale_label = "MADσ" if self._use_mad else "σ"

            return AnomalyEvent(
                timestamp=timestamp,
                session_id=session_id,
                variable=variable,
                anomaly_type=AnomalyType.SPIKE,
                severity=severity,
                message=(
                    f"{variable} spike: {value:.1f} {profile.unit} "
                    f"({z:.1f}{scale_label} {direction} prior mean {mean:.1f})"
                ),
                detail={
                    "value": round(value, 2),
                    "mean": round(mean, 2),
                    "scale": round(scale, 4),
                    "z_score": round(z, 2),
                    "prior_n": int(priors.size),
                    "basis": "prior_window_mean",
                },
            )

        return self._step_jump_spike(
            variable=variable,
            value=value,
            session_id=session_id,
            profile=profile,
            timestamp=timestamp,
            buffer_values=values,
        )

    def _step_jump_spike(
        self,
        *,
        variable: str,
        value: float,
        session_id: int,
        profile: SensorProfile,
        timestamp,
        buffer_values: list[float],
    ) -> Optional[AnomalyEvent]:
        """Catch tall single-tick steps that rolling mean/variance dilute below WARNING z."""

        min_jump = STEP_SPIKE_ABS_MIN.get(variable)
        if min_jump is None or len(buffer_values) < 2:
            return None
        prev_v = float(buffer_values[-2])
        jmp = abs(value - prev_v)
        floor_scale = profile.baseline_noise / self._std_floor_denom
        z_step = jmp / floor_scale if floor_scale else 0.0
        if jmp < min_jump or z_step <= self._warning_z:
            return None
        severity = AlertSeverity.CRITICAL if z_step > self._critical_z else AlertSeverity.WARNING
        direction = "above" if value > prev_v else "below"
        return AnomalyEvent(
            timestamp=timestamp,
            session_id=session_id,
            variable=variable,
            anomaly_type=AnomalyType.SPIKE,
            severity=severity,
            message=(
                f"{variable} spike ({direction} prior reading): {value:.1f} {profile.unit} "
                f"(Δ {jmp:.1f}, {z_step:.1f}σ vs sensor noise floor)"
            ),
            detail={
                "value": round(value, 2),
                "prior_reading": round(prev_v, 2),
                "step_abs": round(jmp, 2),
                "scale_floor": round(floor_scale, 4),
                "z_step": round(z_step, 2),
                "basis": "step_vs_prior_reading",
            },
        )
