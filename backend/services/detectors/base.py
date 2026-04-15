"""
Base classes and shared data structures for all anomaly detectors.

This module defines:
  - Reading:       typed input contract (what the telemetry service sends us)
  - AnomalyEvent:  typed output contract (what we return when something is wrong)
  - SensorProfile: per-sensor thresholds so swapping hardware is a config change
  - BaseDetector:  abstract base class that every detector must implement
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from enums import AnomalyType, AlertSeverity


# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------

@dataclass
class Reading:
    """
    Typed representation of a single sensor reading.

    This is the contract between Bo's telemetry_service and Omer's anomaly
    detection.  Both sides import this class so the interface is explicit
    rather than relying on duck-typing with getattr().

    Any field can be None -- e.g. DHT11 sends null on read failure.
    """
    id: Optional[int] = None
    session_id: int = 0
    timestamp: datetime = field(default_factory=datetime.now)
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    light: Optional[int] = None
    movement: Optional[bool] = None
    distance: Optional[int] = None


@dataclass
class AnomalyEvent:
    """
    A single detected anomaly.  Every detector returns one of these (or None).
    These get persisted to the DB and sent to the alert service + frontend.

    variable:     which sensor channel ("temperature", "humidity", "light", or "all" for dropout)
    anomaly_type: DRIFT / NOISE / DROPOUT  (from enums.py)
    severity:     INFO / WARNING / CRITICAL (from enums.py)
    detail:       detector-specific numbers (slope, std_dev, gap_seconds, etc.)
    """
    timestamp: datetime
    session_id: int
    variable: str
    anomaly_type: AnomalyType
    severity: AlertSeverity
    message: str
    detail: dict = field(default_factory=dict)


@dataclass
class SensorProfile:
    """
    Holds the known characteristics of a single sensor type.
    Each detector reads these to decide its thresholds, so swapping hardware
    (e.g. DHT11 -> BME280) only requires changing the profile -- not every detector.

    baseline_noise:        the normal std dev of readings when the sensor is healthy
    drift_slope_threshold: max acceptable slope (units/reading) before flagging drift
    unit:                  display label ("C", "%RH", "raw")
    """
    baseline_noise: float
    drift_slope_threshold: float
    unit: str


# One profile per monitored variable.  Values come from datasheets and testing:
#   - DHT11 temperature: resolution 1C, accuracy +/-2C, normal jitter ~0.5C
#   - DHT11 humidity:    accuracy +/-5%RH, normal jitter ~2%RH, high noise so
#                         drift threshold is 0.5 (not 0.15) to avoid false positives
#   - LDR:               uncalibrated analog 0-1023, inherently noisy (~20 units)
SENSOR_PROFILES: dict[str, SensorProfile] = {
    "temperature": SensorProfile(baseline_noise=0.5, drift_slope_threshold=0.05, unit="C"),
    "humidity": SensorProfile(baseline_noise=2.0, drift_slope_threshold=0.5, unit="%RH"),
    "light": SensorProfile(baseline_noise=20.0, drift_slope_threshold=3.0, unit="raw"),
}


# ---------------------------------------------------------------------------
# Abstract base class -- the contract every detector must follow
# ---------------------------------------------------------------------------

class BaseDetector(ABC):
    """
    Abstract base class for all anomaly detectors.

    WHY THIS EXISTS:
    Without this, each detector has a detect() method but with different
    signatures (buffer-based vs timestamp-based).  That makes it impossible
    to loop over detectors generically or add a new detector without editing
    the orchestrator.

    With this ABC:
      1. Every detector implements detect_reading(reading, buffer) -> list[AnomalyEvent]
      2. The orchestrator can iterate over a list of BaseDetector instances
      3. Adding a 4th detector (e.g. SpikeDetector) means creating a new class
         that extends BaseDetector -- no changes to the orchestrator

    This follows the Open/Closed Principle: open for extension, closed for
    modification.
    """

    @abstractmethod
    def detect_reading(
        self,
        reading: Reading,
        buffer: object,
        session_id: int,
    ) -> list[AnomalyEvent]:
        """
        Analyse a single incoming reading and return any anomalies found.

        Args:
            reading:    the current sensor reading
            buffer:     the RollingBuffer for this session (detectors that need
                        windowed data use it; dropout detector ignores it)
            session_id: which monitoring session this reading belongs to

        Returns:
            List of AnomalyEvent objects (empty if nothing abnormal)
        """
        ...
