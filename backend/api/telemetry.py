"""
FR1 / FR2 - Environmental Monitoring & Data Logging endpoints.
Ingest sensor readings, query time-series data.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from database import get_db
from services.telemetry_service import get_telemetry_timeseries_data

router = APIRouter()

@router.get("/timeseries")
def get_telemetry_timeseries(
    hours: int = Query(24, description="Time range in hours for historical data"),
    db: Session = Depends(get_db)
):
    return get_telemetry_timeseries_data(db, hours)