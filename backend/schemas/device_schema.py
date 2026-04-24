"""Device registration API."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class DeviceCreate(BaseModel):
    bt_name: Optional[str] = None
    mac: Optional[str] = None
    label: Optional[str] = None


class DeviceUpdate(BaseModel):
    bt_name: Optional[str] = None
    mac: Optional[str] = None
    label: Optional[str] = None


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    bt_name: Optional[str] = None
    mac: Optional[str] = None
    label: Optional[str] = None
    last_seen_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class DeviceListResponse(BaseModel):
    devices: list[DeviceOut]
