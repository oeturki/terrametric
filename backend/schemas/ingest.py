"""Inbound telemetry from Arduino / bridge (matches JSON from arduino_bluetooth.ino)."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class TelemetryIngest(BaseModel):
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    movement: Optional[bool] = None
    light: Optional[int] = None
    distance: Optional[float] = None
    plant_height: Optional[float] = None
    timestamp: Optional[datetime] = None
    device_id: Optional[int] = None
    bt_name: Optional[str] = Field(None, description="Match Device.bt_name if device_id omitted")
    plant_id: Optional[int] = Field(
        None,
        description="When no recording session is open, tag readings to this sample for graphs "
        "and threshold alerts (e.g. set TM_BRIDGE_PLANT_ID on the Pi).",
    )


class TelemetryIngestResult(BaseModel):
    stored: bool
    session_id: Optional[int] = None
    message: Optional[str] = None
