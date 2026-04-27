"""
Recording session: links one sample (plant) to telemetry for a time window.

Policy (your choice): only ONE session may be open (ended_at IS NULL) globally.
Starting a new session closes any other open session in application code.
"""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, Index, text
from sqlalchemy.sql import func
from database import Base


class RecordingSession(Base):
    __tablename__ = "recording_sessions"


    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("plants.id"), nullable=False, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=True, index=True)

    #started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    ended_at = Column(DateTime, nullable=True, index=True)

    setpoint_temp = Column(Float, nullable=True)
    setpoint_humidity = Column(Float, nullable=True)
    setpoint_light = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    #started_by = Column(Integer, nullable=True)  # user id when auth exists
    started_by = Column(Integer, ForeignKey("users.id"), nullable=True)


    # Dummy-data engine metadata (Phase 2). Persist on the session so /sessions/active
    # can tell the UI what scenario is running, and so the lifespan task knows what
    # generator to use. Real Arduino sessions leave dummy_stream=False.
    scenario = Column(String(32), nullable=True)
    #dummy_stream = Column(Boolean, nullable=False, server_default="False")
    dummy_stream = Column(Boolean, nullable=False, server_default=text("0"))
    #stream_interval_sec = Column(Integer, nullable=True)
    stream_interval_sec = Column(Integer, nullable=False, server_default="1")

    __table_args__ = (
        Index(
            "one_open_session",
            ended_at,
            unique=True,
            postgresql_where=(ended_at.is_(None)),
        ),
    )