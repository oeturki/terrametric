"""
Registered Arduino / BLE bridge devices.
One row per physical device (identified by Bluetooth name or MAC).
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from database import Base


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    bt_name = Column(String(64), nullable=True, index=True)  # e.g. Group14 from AT+NAME
    mac = Column(String(32), nullable=True, unique=True, index=True)
    label = Column(String(128), nullable=True)  # human-readable label
    last_seen_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
