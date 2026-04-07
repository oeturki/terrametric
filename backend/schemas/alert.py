"""
FR3 - Request/response schemas for alert endpoints.
"""

from pydantic import BaseModel
from datetime import datetime
from typing import Optional


# TODO: AlertResponse - id, session_id, timestamp, variable, deviation, severity, acknowledged, message
# TODO: AlertAcknowledge - alert_id: int
