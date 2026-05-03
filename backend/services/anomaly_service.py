"""
FR10 - Anomaly Detection Service  [Owner: Omer]

Real-time detection of drift, noise, and dropout anomalies in environmental
sensor data. Runs independently per variable (temperature, humidity, light).

Integration:
  - Called by: telemetry_service.store_reading() after persisting each reading
  - Outputs to: alert_service (notifications), report_service (summaries), API (frontend)

Architecture:
  This file is the ORCHESTRATOR.  It does not contain detection logic itself.
  Each detector lives in its own module under services/detectors/:

    detectors/
      base.py           - BaseDetector ABC, Reading, AnomalyEvent, SensorProfile
      rolling_buffer.py - RollingBuffer (sliding window)
      drift.py          - DriftDetector  (linear regression slope)
      noise.py          - NoiseDetector  (rolling std dev)
      dropout.py        - DropoutDetector (timestamp gap analysis)

  Adding a new detector (e.g. SpikeDetector) means:
    1. Create detectors/spike.py extending BaseDetector
    2. Add it to self._detectors list in __init__ below
    3. No other changes needed (Open/Closed Principle)
"""

from __future__ import annotations

from typing import Optional

from enums import EnvironmentVariable

# All public types re-exported so other services can do:
#   from services.anomaly_service import AnomalyDetectionService, Reading, AnomalyEvent
from services.detectors import (
    BaseDetector,
    Reading,
    AnomalyEvent,
    SensorProfile,
    SENSOR_PROFILES,
    RollingBuffer,
    DriftDetector,
    NoiseDetector,
    DropoutDetector,
    MissingChannelDetector,
    SpikeDetector,
    CorrelationDetector,
    CUSUMDetector,
    EWMADetector,
    SeasonalDetector,
)
from services.detectors.residual_light_cusum import LightResidualCUSUMDetector


# The three environmental variables we run anomaly detection on.
# PIR (movement) and HC-SR04 (distance) are excluded -- they're not continuous signals.
MONITORED_VARIABLES = [
    EnvironmentVariable.TEMPERATURE,
    EnvironmentVariable.HUMIDITY,
    EnvironmentVariable.LIGHT,
]


class AnomalyDetectionService:
    """
    The main orchestrator.  Bo's telemetry_service calls process_reading() after
    every new reading is stored.  This class:

      1. Checks for data gaps (dropout)
      2. For each of the 3 monitored variables (temp, humidity, light):
         a. Skips if the value is null (DHT11 read failure)
         b. Adds the value to the rolling buffer
         c. Runs each detector on the buffer
      3. Returns all anomaly events found (may be empty)

    Maintains a separate RollingBuffer per session so concurrent sessions
    don't interfere with each other.  Memory cost is negligible (~40KB at
    50 sessions).

    EXTENSIBILITY:
    All detectors are stored in self._detectors as a list of BaseDetector.
    To add a new detector, instantiate it and append to the list -- the
    process_reading() loop doesn't need to change.
    """

    def __init__(
        self,
        profiles: dict[str, SensorProfile] | None = None,
        drift_window: int = 30,           # how many readings the drift detector looks at
        noise_window: int = 10,           # how many readings the noise detector looks at
        noise_warn_mult: float = 3.0,     # noise WARNING at 3x baseline
        noise_crit_mult: float = 5.0,     # noise CRITICAL at 5x baseline
        dropout_multiplier: int = 3,      # gap must be 3x expected to flag
        dropout_baseline_count: int = 20,   # learn expected interval from first 20 readings
        dropout_severity_warning_ratio: int = 5,
        dropout_severity_critical_ratio: int = 15,
        spike_warning_z: float = 4.0,
        spike_critical_z: float = 6.0,
        spike_std_floor_denom: float = 4.0,
        spike_min_prior: int = 5,
        spike_min_abs_delta: float = 0.0,
        spike_use_mad: bool = False,
        drift_min_r_squared: float = 0.12,
        drift_mk_suppress: bool = False,
        drift_mk_p_max: float = 0.15,
        core_light_residual_cusum: bool = False,
        residual_cusum_k: float = 0.35,
        residual_cusum_h: float = 4.0,
        residual_cusum_window: int = 15,
        residual_cusum_min_prior: int = 8,
        missing_channel_enabled: bool = True,
        missing_channel_consec_warning: int = 4,
        missing_channel_consec_critical: int = 8,
        missing_channel_require_peer_signal: bool = True,
        extended_detectors: bool = False,
    ):
        profiles = profiles or SENSOR_PROFILES
        self._variables = [v.value for v in MONITORED_VARIABLES]
        self._drift_window = drift_window
        self._noise_window = noise_window

        self._buffers: dict[int, RollingBuffer] = {}

        self._dropout = DropoutDetector(
            dropout_multiplier,
            dropout_baseline_count,
            dropout_severity_warning_ratio,
            dropout_severity_critical_ratio,
        )
        self._correlation = CorrelationDetector(window_size=noise_window)
        self._cusum = CUSUMDetector(profiles)
        self._ewma = EWMADetector(profiles)
        self._seasonal = SeasonalDetector()
        self._missing_channel: Optional[MissingChannelDetector] = None
        self._light_residual_cusum: Optional[LightResidualCUSUMDetector] = None

        spike = SpikeDetector(
            profiles,
            warning_z=spike_warning_z,
            critical_z=spike_critical_z,
            std_floor_denom=spike_std_floor_denom,
            min_prior=spike_min_prior,
            min_abs_delta=spike_min_abs_delta,
            use_mad=spike_use_mad,
        )

        drift = DriftDetector(
            profiles,
            drift_window,
            min_r_squared=drift_min_r_squared,
            use_mk_suppression=drift_mk_suppress,
            mk_p_max=drift_mk_p_max,
        )
        noise = NoiseDetector(profiles, noise_window, noise_warn_mult, noise_crit_mult)

        core: list[BaseDetector] = [self._dropout]
        if missing_channel_enabled:
            self._missing_channel = MissingChannelDetector(
                list(self._variables),
                consec_warning=missing_channel_consec_warning,
                consec_critical=missing_channel_consec_critical,
                require_peer_non_null=missing_channel_require_peer_signal,
            )
            core.append(self._missing_channel)
        core.extend([spike, drift])
        # Optional change-point-lite: mutually exclusive with extended's full CUSUM in simulate.
        if core_light_residual_cusum and not extended_detectors:
            self._light_residual_cusum = LightResidualCUSUMDetector(
                profiles,
                allowance_k=residual_cusum_k,
                decision_h=residual_cusum_h,
                baseline_window=residual_cusum_window,
                min_prior=residual_cusum_min_prior,
            )
            core.append(self._light_residual_cusum)
        core.append(noise)

        extended: list[BaseDetector] = [
            self._correlation,
            self._cusum,
            self._ewma,
            self._seasonal,
        ]
        self._detectors = core + (extended if extended_detectors else [])
    def _stream_key(self, reading: Reading) -> int:
        """Isolate detector state per sample (plant) when available; else recording session / lab id."""
        if reading.plant_id is not None:
            return int(reading.plant_id)
        return int(reading.session_id)

    def _get_buffer(self, stream_key: int) -> RollingBuffer:
        """Lazily create a buffer for this stream. Buffer size = max of both windows."""
        if stream_key not in self._buffers:
            max_size = max(self._drift_window, self._noise_window)
            self._buffers[stream_key] = RollingBuffer(max_size)
        return self._buffers[stream_key]

    def process_reading(self, reading: Reading) -> list[AnomalyEvent]:
        """
        Main entry point -- called once for every incoming sensor reading.

        Args:
            reading: a Reading dataclass with .session_id, .timestamp,
                     .temperature, .humidity, .light (any can be None)

        Returns:
            List of AnomalyEvent objects detected (empty list if everything is normal)
        """
        events: list[AnomalyEvent] = []
        stream_key = self._stream_key(reading)
        timestamp = reading.timestamp
        buffer = self._get_buffer(stream_key)

        # Add non-null values to the rolling buffer before running detectors
        variable_values = {
            "temperature": reading.temperature,
            "humidity": reading.humidity,
            "light": reading.light,
        }

        for var in self._variables:
            value = variable_values.get(var)
            # DHT11 sends null on read failure -- skip this variable for this reading
            if value is None:
                continue
            buffer.add(var, timestamp, float(value))

        # Run every detector through the common interface
        for detector in self._detectors:
            events.extend(detector.detect_reading(reading, buffer, stream_key))

        return events

    def get_anomaly_summary(self, session_id: int, events: list[AnomalyEvent]) -> dict:
        """
        Build a summary dictionary for Jena's report service (FR11).
        Groups events by type and variable for easy display in session reports.
        """
        summary: dict = {
            "session_id": session_id,
            "total_count": len(events),
            "by_type": {},       # e.g. {"drift": 3, "noise": 1}
            "by_variable": {},   # e.g. {"temperature": 2, "humidity": 2}
            "events": [],
        }
        for evt in events:
            t = evt.anomaly_type.value
            summary["by_type"][t] = summary["by_type"].get(t, 0) + 1
            v = evt.variable
            summary["by_variable"][v] = summary["by_variable"].get(v, 0) + 1
            summary["events"].append({
                "timestamp": evt.timestamp.isoformat(),
                "variable": evt.variable,
                "type": t,
                "severity": evt.severity.value,
                "message": evt.message,
            })
        return summary

    def reset(self, stream_key: int) -> None:
        """Clean up detector state for a plant (sample) or lab session id."""
        self._buffers.pop(stream_key, None)
        self._dropout.reset(stream_key)
        if self._missing_channel:
            self._missing_channel.reset(stream_key)
        self._correlation.reset(stream_key)
        self._cusum.reset(stream_key)
        self._ewma.reset(stream_key)
        self._seasonal.reset(stream_key)
        if self._light_residual_cusum:
            self._light_residual_cusum.reset(stream_key)


def anomaly_detection_constructor_kwargs(extended_detectors: bool | None = None) -> dict:
    """
    Build ``AnomalyDetectionService(...)`` kwargs from ``config.settings`` (.env aligned).
    When ``extended_detectors`` is None, uses ``settings.FR10_EXTENDED_DETECTORS``.
    Synthetic lab passes ``extended_detectors=True`` explicitly so all rule packs run together.
    """
    from config import settings

    ext = extended_detectors if extended_detectors is not None else settings.FR10_EXTENDED_DETECTORS
    return {
        "drift_window": settings.DRIFT_WINDOW_SIZE,
        "noise_window": settings.NOISE_WINDOW_SIZE,
        "noise_warn_mult": settings.NOISE_MULTIPLIER_WARNING,
        "noise_crit_mult": settings.NOISE_MULTIPLIER_CRITICAL,
        "dropout_multiplier": settings.DROPOUT_MULTIPLIER,
        "dropout_baseline_count": settings.DROPOUT_BASELINE_READINGS,
        "dropout_severity_warning_ratio": settings.DROPOUT_SEVERITY_WARNING,
        "dropout_severity_critical_ratio": settings.DROPOUT_SEVERITY_CRITICAL,
        "spike_warning_z": settings.SPIKE_WARNING_Z,
        "spike_critical_z": settings.SPIKE_CRITICAL_Z,
        "spike_std_floor_denom": settings.SPIKE_STD_FLOOR_DENOM,
        "spike_min_prior": settings.SPIKE_MIN_PRIOR,
        "spike_min_abs_delta": settings.SPIKE_MIN_ABS_DELTA,
        "spike_use_mad": settings.SPIKE_USE_MAD,
        "drift_min_r_squared": settings.DRIFT_MIN_R_SQUARED,
        "drift_mk_suppress": settings.FR10_DRIFT_MK_SUPPRESS,
        "drift_mk_p_max": settings.FR10_DRIFT_MK_P_MAX,
        "core_light_residual_cusum": settings.FR10_CORE_LIGHT_RESIDUAL_CUSUM,
        "residual_cusum_k": settings.RESIDUAL_CUSUM_K,
        "residual_cusum_h": settings.RESIDUAL_CUSUM_H,
        "residual_cusum_window": settings.RESIDUAL_CUSUM_WINDOW,
        "residual_cusum_min_prior": settings.RESIDUAL_CUSUM_MIN_PRIOR,
        "missing_channel_enabled": settings.MISSING_CHANNEL_ENABLED,
        "missing_channel_consec_warning": settings.MISSING_CHANNEL_CONSEC_WARNING,
        "missing_channel_consec_critical": settings.MISSING_CHANNEL_CONSEC_CRITICAL,
        "missing_channel_require_peer_signal": settings.MISSING_CHANNEL_REQUIRE_PEER_SIGNAL,
        "extended_detectors": ext,
    }
