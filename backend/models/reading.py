"""
FR1/FR2 - Sensor Reading model.
Timestamped environmental telemetry records.
"""

from sqlalchemy import Column, Integer, Float, Boolean, DateTime
from datetime import datetime
from database import Base


class Telemetry(Base):
    __tablename__ = "telemetry"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    temperature = Column(Float, nullable=True)
    humidity = Column(Float, nullable=True)
    light = Column(Float, nullable=True)
    movement = Column(Boolean, nullable=True)
    distance = Column(Float, nullable=True)

