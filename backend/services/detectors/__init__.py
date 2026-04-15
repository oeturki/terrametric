"""
Anomaly detection sub-package.

Each detector lives in its own module and implements the BaseDetector protocol.
The orchestrator (anomaly_service.py) imports from here.
"""

from .base import BaseDetector, Reading, AnomalyEvent, SensorProfile, SENSOR_PROFILES
from .rolling_buffer import RollingBuffer
from .drift import DriftDetector
from .noise import NoiseDetector
from .dropout import DropoutDetector

__all__ = [
    "BaseDetector",
    "Reading",
    "AnomalyEvent",
    "SensorProfile",
    "SENSOR_PROFILES",
    "RollingBuffer",
    "DriftDetector",
    "NoiseDetector",
    "DropoutDetector",
]
