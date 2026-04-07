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

    # Anomaly detection
    SPIKE_THRESHOLD_TEMP: float = 5.0
    DRIFT_WINDOW_MINUTES: int = 60
    DRIFT_SLOPE_THRESHOLD: float = 0.1
    MISSING_DATA_GAP_THRESHOLD: int = 5

    # JWT auth
    SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    class Config:
        env_file = ".env"


settings = Settings()
