"""
Centralised configuration: database, MQTT broker, setpoints, thresholds.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "sqlite:///./greenhouse.db"

    # MQTT (ThingsBoard / Node-RED)
    MQTT_BROKER_HOST: str = "localhost"
    MQTT_BROKER_PORT: int = 1883
    MQTT_TOPIC_TELEMETRY: str = "v1/devices/me/telemetry"

    # Sampling
    SAMPLING_INTERVAL_SEC: int = 60

    # Environmental setpoints (defaults - overridable per session)
    SETPOINT_TEMPERATURE: float = 22.0
    SETPOINT_HUMIDITY: float = 55.0
    SETPOINT_LIGHT: int = 500

    # Alert thresholds
    THRESHOLD_TEMP_DEVIATION: float = 2.0
    THRESHOLD_HUMIDITY_DEVIATION: float = 10.0
    THRESHOLD_LIGHT_DEVIATION_PCT: float = 15.0

    # Control tolerances
    CONTROL_TOLERANCE_TEMP: float = 1.0
    CONTROL_TOLERANCE_HUMIDITY: float = 5.0

    # Anomaly detection -- drift
    DRIFT_WINDOW_SIZE: int = 30
    DRIFT_SLOPE_THRESHOLD_TEMP: float = 0.05
    DRIFT_SLOPE_THRESHOLD_HUMIDITY: float = 0.5
    DRIFT_SLOPE_THRESHOLD_LIGHT: float = 3.0

    # Anomaly detection -- noise
    NOISE_WINDOW_SIZE: int = 10
    NOISE_BASELINE_TEMP: float = 0.5
    NOISE_BASELINE_HUMIDITY: float = 2.0
    NOISE_BASELINE_LIGHT: float = 20.0
    NOISE_MULTIPLIER_WARNING: float = 3.0
    NOISE_MULTIPLIER_CRITICAL: float = 5.0

    # Anomaly detection -- dropout
    DROPOUT_MULTIPLIER: int = 3
    DROPOUT_BASELINE_READINGS: int = 20
    DROPOUT_SEVERITY_WARNING: int = 5
    DROPOUT_SEVERITY_CRITICAL: int = 15

    # JWT auth
    SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    class Config:
        env_file = ".env"


settings = Settings()
