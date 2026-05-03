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
from .missing_channel import MissingChannelDetector
from .spike import SpikeDetector
from .residual_light_cusum import LightResidualCUSUMDetector
from .correlation import CorrelationDetector
from .cusum import CUSUMDetector
from .ewma import EWMADetector
from .seasonal import SeasonalDetector

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
    "MissingChannelDetector",
    "SpikeDetector",
    "LightResidualCUSUMDetector",
    "CorrelationDetector",
    "CUSUMDetector",
    "EWMADetector",
    "SeasonalDetector",
]
