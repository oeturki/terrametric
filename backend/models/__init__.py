"""
Import all SQLAlchemy models so Base.metadata knows every table before create_all().
Order: users, plants/devices, recording_sessions, telemetry (FKs).
"""

from models.user import User  # noqa: F401
from models.plant import Plant  # noqa: F401
from models.anomaly_detection_event import AnomalyDetectionEvent  # noqa: F401
from models.plant_control import PlantControl  # noqa: F401
from models.device import Device  # noqa: F401
from models.session import RecordingSession  # noqa: F401
from models.reading import Telemetry  # noqa: F401
from models.telemetry_ml_prediction import TelemetryMlPrediction  # noqa: F401
from models.audit_log import AuditLog  # noqa: F401
from models.alert import Alert  # noqa: F401
from models.plant_capture import PlantCapture  # noqa: F401
