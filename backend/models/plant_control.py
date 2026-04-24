"""
Per-plant (sample) control profile: JSON thresholds and camera options.
One row per plant; created with defaults when a plant is inserted.
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text

from database import Base


class PlantControl(Base):
    __tablename__ = "plant_control"

    plant_id = Column(Integer, ForeignKey("plants.id", ondelete="CASCADE"), primary_key=True, index=True)
    profile_json = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
