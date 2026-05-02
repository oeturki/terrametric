"""
Shadow table: optional ML multiclass labels per telemetry row (batch or stream).
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint

from database import Base


class TelemetryMlPrediction(Base):
    __tablename__ = "telemetry_ml_predictions"
    __table_args__ = (UniqueConstraint("telemetry_id", name="uq_telemetry_ml_predictions_telemetry_id"),)

    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("plants.id", ondelete="CASCADE"), nullable=False, index=True)
    telemetry_id = Column(Integer, ForeignKey("telemetry.id", ondelete="CASCADE"), nullable=False, index=True)
    predicted_class = Column(String(32), nullable=False)
    feature_version = Column(String(16), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
