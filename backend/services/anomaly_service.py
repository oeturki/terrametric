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
    SpikeDetector,
    CorrelationDetector,
    CUSUMDetector,
    EWMADetector,
    SeasonalDetector,
)


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
        dropout_baseline_count: int = 20,  # learn expected interval from first 20 readings
        extended_detectors: bool = False,  # add correlation, CUSUM, EWMA, seasonal (see FR10_EXTENDED_DETECTORS)
    ):
        profiles = profiles or SENSOR_PROFILES
        self._variables = [v.value for v in MONITORED_VARIABLES]  # ["temperature", "humidity", "light"]
        self._drift_window = drift_window
        self._noise_window = noise_window

        # One buffer per logical stream (prefer plant_id for live data; else session_id for lab/simulation).
        self._buffers: dict[int, RollingBuffer] = {}

        # Detectors that maintain per-session state and need explicit reset()
        self._dropout = DropoutDetector(dropout_multiplier, dropout_baseline_count)
        self._correlation = CorrelationDetector(window_size=noise_window)
        self._cusum = CUSUMDetector(profiles)
        self._ewma = EWMADetector(profiles)
        self._seasonal = SeasonalDetector()

        # All detectors in a single list, iterated by process_reading().
        # Core set is testable baseline; extended rules are assumption-heavy (sampling structure).
        spike = SpikeDetector(profiles)
        core: list[BaseDetector] = [
            self._dropout,
            spike,
            DriftDetector(profiles, drift_window),
            NoiseDetector(profiles, noise_window, noise_warn_mult, noise_crit_mult),
        ]
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
        self._correlation.reset(stream_key)
        self._cusum.reset(stream_key)
        self._ewma.reset(stream_key)
        self._seasonal.reset(stream_key)
