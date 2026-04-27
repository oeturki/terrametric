"""
FR7 - Plant / Tray (sample) model.
Matches Manage Samples form fields plus GMO research metadata.
"""

from datetime import date, datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint

from database import Base


class Plant(Base):
    __tablename__ = "plants"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(256), nullable=False, default="Unnamed Plant")
    location = Column(String(256), nullable=True)
    germination_date = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)
    # Unique per owner so different accounts may reuse the same label (e.g. TM-S001).
    qr_code = Column(String(128), nullable=True, index=True)

    species = Column(String(256), nullable=True)
    genotype = Column(String(256), nullable=True)
    treatment_group = Column(String(128), nullable=True)
    parent_plant_id = Column(Integer, ForeignKey("plants.id"), nullable=True)
    generation = Column(Integer, nullable=True)
    lifecycle_state = Column(String(32), nullable=True, default="registered")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(Integer, nullable=True)  # legacy mirror of owner
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    __table_args__ = (UniqueConstraint("owner_id", "qr_code", name="uq_plants_owner_qr"),)
