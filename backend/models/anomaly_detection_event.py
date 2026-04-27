"""
Persisted outputs from FR10 anomaly detectors (live / dummy ingest), keyed to telemetry rows.
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from database import Base


class AnomalyDetectionEvent(Base):
    __tablename__ = "anomaly_detection_events"

    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("plants.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("recording_sessions.id"), nullable=True, index=True)
    telemetry_id = Column(Integer, ForeignKey("telemetry.id", ondelete="SET NULL"), nullable=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    anomaly_type = Column(String(32), nullable=False)
    variable = Column(String(64), nullable=False)
    severity = Column(String(16), nullable=False)
    message = Column(Text, nullable=True)
    detail_json = Column(Text, nullable=True)
