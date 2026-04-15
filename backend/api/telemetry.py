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
    """
    API endpoint for frontend time-series graphs.
    Returns structured sensor data with timestamps.
    """
    records = get_telemetry_timeseries_data(db, hours)

    formatted_data = []
    for record in records:
        formatted_data.append({
            "timestamp": record.timestamp.isoformat(),
            "temperature": record.temperature,
            "humidity": record.humidity,
            "light": record.light
        })

    return {
        "time_range_hours": hours,
        "timezone": "UTC",
        "sensor_data": formatted_data
    }
