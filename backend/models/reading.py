"""
FR1/FR2 - Sensor Reading model.
Timestamped environmental telemetry records.

session_id links a row to an open or closed RecordingSession (hence to a plant).
When no session is active, session_id may be NULL (raw stream still storable).
"""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, Index

from database import Base


class Telemetry(Base):
    __tablename__ = "telemetry"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("recording_sessions.id"), nullable=True, index=True)
    # Denormalised at ingest for fast per-sample graphs (copied from open RecordingSession.plant_id)
    plant_id = Column(Integer, ForeignKey("plants.id"), nullable=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    temperature = Column(Float, nullable=True)
    humidity = Column(Float, nullable=True)
    light = Column(Float, nullable=True)
    movement = Column(Boolean, nullable=True)
    distance = Column(Float, nullable=True)
    # Used by charts when height comes from vision/other; Arduino sends distance (ultrasonic)
    plant_height = Column(Float, nullable=True)

    __table_args__ = (
        Index("ix_telemetry_session_timestamp", "session_id", "timestamp"),
        Index("ix_telemetry_plant_timestamp", "plant_id", "timestamp"),
    )

