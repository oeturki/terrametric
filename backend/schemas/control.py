"""
FR4 - Request/response schemas for control endpoints.
"""

from pydantic import BaseModel
from typing import Optional


# TODO: SetpointUpdate - temperature: Optional[float], humidity: Optional[float], light: Optional[int]
# TODO: ManualOverride - actuator: ActuatorType, state: bool
# TODO: ControlActionResponse - id, session_id, timestamp, actuator, action, trigger_type
