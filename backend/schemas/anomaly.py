"""
FR10 - Anomaly detection request/response schemas.
"""

from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class AnomalyEventResponse(BaseModel):
    id: Optional[int] = None
    session_id: int
    timestamp: datetime
    variable: str
    anomaly_type: str
    severity: str
    message: str
    detail: dict = {}


class AnomalySummaryResponse(BaseModel):
    session_id: int
    total_count: int
    by_type: dict = {}
    by_variable: dict = {}
    events: list[AnomalyEventResponse] = []
