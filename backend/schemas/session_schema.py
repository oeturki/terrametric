"""
Recording session API shapes (file named session_schema to avoid clashing with sqlalchemy.orm.Session).
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# Single source of truth for valid simulator profiles — also imported by dummy_stream
# so adding a scenario in one place is enough.
ScenarioName = Literal["stable", "heat_spike", "drought", "cold_night", "sensor_drift"]


class RecordingSessionStart(BaseModel):
    """POST /api/sessions/start — exactly one active session globally; this closes any other open session."""

    plant_id: int
    device_id: Optional[int] = None
    setpoint_temp: Optional[float] = None
    setpoint_humidity: Optional[float] = None
    setpoint_light: Optional[float] = None
    notes: Optional[str] = None

    # Phase 2: dummy-data engine. Real Arduino sessions leave dummy_stream=False.
    dummy_stream: bool = False
    scenario: Optional[ScenarioName] = "stable"
    stream_interval_sec: int = Field(5, ge=1, le=300)


class RecordingSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plant_id: int
    device_id: Optional[int] = None
    started_at: datetime
    ended_at: Optional[datetime] = None
    setpoint_temp: Optional[float] = None
    setpoint_humidity: Optional[float] = None
    setpoint_light: Optional[float] = None
    notes: Optional[str] = None
    scenario: Optional[str] = None
    dummy_stream: bool = False
    stream_interval_sec: Optional[int] = None


class ActiveSessionsResponse(BaseModel):
    """At most one session when policy is single-active-sample."""

    sessions: list[RecordingSessionOut]


class RecordingSessionListResponse(BaseModel):
    sessions: list[RecordingSessionOut]
