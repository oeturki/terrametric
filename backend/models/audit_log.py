"""
Append-only audit trail for plant edits and recording session lifecycle.
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from database import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    entity_type = Column(String(64), nullable=False, index=True)
    entity_id = Column(Integer, nullable=True, index=True)
    action = Column(String(64), nullable=False)
    user_id = Column(Integer, nullable=True)
    at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    payload_json = Column(Text, nullable=True)
