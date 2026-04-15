"""
Shared enums and constants used across services, models, and API routes.
Prevents magic strings and keeps the codebase consistent.
"""

from enum import Enum


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AnomalyType(str, Enum):
    SPIKE = "spike"
    DRIFT = "drift"
    NOISE = "noise"
    DROPOUT = "dropout"
    MISSING_DATA = "missing_data"


class TriggerType(str, Enum):
    AUTO = "auto"
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    ALERT = "alert"


class ActuatorType(str, Enum):
    FAN = "fan"
    LIGHT = "light"
    IRRIGATION = "irrigation"


class SessionStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ABORTED = "aborted"


class EnvironmentVariable(str, Enum):
    TEMPERATURE = "temperature"
    HUMIDITY = "humidity"
    LIGHT = "light"
