"""
FR3 - Threshold and system alerts. Persisted for /api/alerts/active and history.
"""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text

from database import Base


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("plants.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("recording_sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    variable = Column(String(64), nullable=False, index=True)
    severity = Column(String(32), nullable=False)  # warning | danger
    title = Column(String(256), nullable=True)
    message = Column(Text, nullable=False)
    acknowledged = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
