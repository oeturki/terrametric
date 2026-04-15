"""
Session request/response schemas.
"""

from pydantic import BaseModel
from datetime import datetime
from typing import Optional


# TODO: SessionCreate - setpoint_temp, setpoint_humidity, setpoint_light, plant_ids (optional)
# TODO: SessionResponse - id, user_id, start_time, end_time, setpoints, status, esi, stress
