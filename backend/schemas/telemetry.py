"""
FR1/FR2 - Request/response schemas for telemetry endpoints.
These define what the API accepts and returns (separate from DB models).
"""

from pydantic import BaseModel
from datetime import datetime
from typing import Optional


# TODO: ReadingCreate - what the client sends when posting a new reading
#   session_id: int
#   temperature: Optional[float]
#   humidity: Optional[float]
#   light: Optional[int]
#   movement: Optional[bool]
#   distance: Optional[float]

# TODO: ReadingResponse - what the API returns
#   id: int
#   session_id: int
#   timestamp: datetime
#   temperature, humidity, light, movement, distance

