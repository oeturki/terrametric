"""
Centralised configuration: database, MQTT broker, setpoints, thresholds.
"""

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Always load backend/.env regardless of process cwd (fixes missing HARDWARE_PI_KEY when
# uvicorn is started from the repo root).
_ENV_FILE = Path(__file__).resolve().parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8-sig",
        extra="ignore",
    )
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
    # Balanced preset: OLS slope on a prior-only window; skip wobbly fits (low R²); optional MK gate below.
    DRIFT_WINDOW_SIZE: int = 30
    DRIFT_SLOPE_THRESHOLD_TEMP: float = 0.05
    DRIFT_SLOPE_THRESHOLD_HUMIDITY: float = 0.5
    DRIFT_SLOPE_THRESHOLD_LIGHT: float = 3.0
    DRIFT_MIN_R_SQUARED: float = 0.12
    # When True, suppress drift if Kendall tau trend p-value is above threshold (non-monotonic / wobbly).
    FR10_DRIFT_MK_SUPPRESS: bool = False
    FR10_DRIFT_MK_P_MAX: float = 0.15

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

    # Dead / unreadable monitored channel while other env fields still post (MISSING_DATA).
    MISSING_CHANNEL_ENABLED: bool = True
    MISSING_CHANNEL_CONSEC_WARNING: int = 4
    MISSING_CHANNEL_CONSEC_CRITICAL: int = 8
    # Require at least one other monitored env var non-null on the same ingest row before counting.
    MISSING_CHANNEL_REQUIRE_PEER_SIGNAL: bool = True

    # Anomaly detection -- spike (z vs prior-only window; std floor from baseline_noise / denom)
    SPIKE_WARNING_Z: float = 4.0
    SPIKE_CRITICAL_Z: float = 6.0
    SPIKE_STD_FLOOR_DENOM: float = 4.0
    SPIKE_MIN_PRIOR: int = 5
    # Absolute deviation from prior mean must exceed this (same units as sensor) to count as spike at WARNING+.
    SPIKE_MIN_ABS_DELTA: float = 0.0
    SPIKE_USE_MAD: bool = False

    # Optional core detector: light residual CUSUM (LEVEL_SHIFT). Off by default; omitted when extended_detectors
    # is True to avoid overlapping with the full CUSUM detector in the synthetic lab.
    FR10_CORE_LIGHT_RESIDUAL_CUSUM: bool = False
    RESIDUAL_CUSUM_K: float = 0.35
    RESIDUAL_CUSUM_H: float = 4.0
    RESIDUAL_CUSUM_WINDOW: int = 15
    RESIDUAL_CUSUM_MIN_PRIOR: int = 8

    # When True, enable correlation, CUSUM (level shift), EWMA, and seasonal detectors in addition
    # to the default core set (dropout, spike, drift, noise). Synthetic lab always runs extended rules.
    FR10_EXTENDED_DETECTORS: bool = False

    # Synthetic HTTP lab (removed from SPA). Enable explicitly for demos/API tests.
    ALLOW_ANOMALY_SIMULATE: bool = False

    # Sklearn multiclass model on stored telemetry (see docs/ml-classifier.md).
    # Shipped artifact under ML_CLASSIFIER_MODEL_PATH; batch classify via POST /api/ml/classify/window.
    ML_ANOM_CLASSIFIER_ENABLED: bool = True
    # Path resolved relative to the backend package directory (where config.py lives).
    ML_CLASSIFIER_MODEL_PATH: str = "artifacts/anomaly_classifier.joblib"

    # JWT auth
    SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_ALGORITHM: str = "HS256"

    # Proxy to the Pi hardware agent (see `pi/hardware_agent.py`). Set on the *laptop* Uvicorn host only.
    HARDWARE_PI_BASE: str = ""  # e.g. http://PI_IP_ADDRESS:8765 when hardware_agent runs on the Pi LAN IP
    HARDWARE_PI_KEY: str = ""  # same as DEVICE_KEY on the Pi; never expose to the browser

    # When Pi is configured, turn ventilation on/off from desired band during active recording sessions.
    AUTO_VENTILATION_ENABLED: bool = True

    # Stored Pi camera JPEGs (path on the API host; not in git by default).
    CAPTURE_STORAGE_DIR: str = ""

    # Demo: POST /api/auth/register-admin requires this body field ``admin_secret`` when set
    ADMIN_REGISTRATION_SECRET: str = ""

    # When the DB has zero users, create one demo account and attach migrated plants to it
    TERRA_BOOTSTRAP_DEMO_USER: bool = True
    TERRA_DEMO_EMAIL: str = "demo@example.com"
    TERRA_DEMO_PASSWORD: str = "demo"

    @field_validator("HARDWARE_PI_KEY", "HARDWARE_PI_BASE", mode="before")
    @classmethod
    def _strip_hardware_env(cls, v: object) -> str:
        if v is None:
            return ""
        return str(v).strip()


settings = Settings()
