"""
FR1/FR2 - Sensor Reading model.
Timestamped environmental telemetry records.
"""

# TODO: Reading table - id, session_id, timestamp, temperature, humidity, light, movement, distance
from sqlalchemy import Column, Integer, Float, DateTime
from datetime import datetime
from database import Base

class Telemetry(Base):
    __tablename__ = "telemetry"

    id = Column(Integer, primary_key=True, index=True)
    temperature = Column(Float, nullable=False)
    humidity = Column(Float, nullable=False)
    light = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)