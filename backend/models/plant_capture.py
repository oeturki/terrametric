"""
Persisted JPEG captures from the Pi camera, scoped to a plant (sample) and optional session.
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text

from database import Base


class PlantCapture(Base):
    __tablename__ = "plant_captures"

    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("plants.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("recording_sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    telemetry_id = Column(Integer, ForeignKey("telemetry.id", ondelete="SET NULL"), nullable=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    trigger = Column(String(32), nullable=False)  # manual | interval | desired_breach | motion
    detail = Column(String(256), nullable=True)
    storage_path = Column(String(512), nullable=False)
    height_cm = Column(Float, nullable=True)
