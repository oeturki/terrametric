"""
Import all SQLAlchemy models so Base.metadata knows every table before create_all().
Order: plants/devices first, then recording_sessions, then telemetry (FKs to sessions).
"""

from models.plant import Plant  # noqa: F401
from models.device import Device  # noqa: F401
from models.session import RecordingSession  # noqa: F401
from models.reading import Telemetry  # noqa: F401
from models.audit_log import AuditLog  # noqa: F401
