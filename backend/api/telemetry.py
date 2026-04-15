"""
FR1 / FR2 - Environmental Monitoring & Data Logging endpoints.
Ingest sensor readings, query time-series data.
"""

from fastapi import APIRouter

router = APIRouter()


# TODO: POST /readings - ingest a new sensor reading
# TODO: GET  /readings - query readings with time range filters
# TODO: GET  /readings/latest - get most recent reading

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from schemas.telemetry import TelemetryCreate, TelemetryResponse
from services.telemetry_service import create_telemetry, get_telemetry_list, get_recent_telemetry
from services.esi_service import calculate_esi
from services.stress_service import calculate_cumulative_stress

router = APIRouter(prefix="/telemetry", tags=["telemetry"])

@router.post("/", response_model=TelemetryResponse)
def add_telemetry(data: TelemetryCreate, db: Session = Depends(get_db)):
    return create_telemetry(db, data)

@router.get("/", response_model=list[TelemetryResponse])
def list_telemetry(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return get_telemetry_list(db, skip, limit)

@router.get("/esi")
def get_esi(minutes: int = 10, db: Session = Depends(get_db)):
    data = get_recent_telemetry(db, minutes)
    dicts = [{"temperature": d.temperature, "humidity": d.humidity} for d in data]
    esi = calculate_esi(dicts)
    return {"esi": esi, "time_window_minutes": minutes}

@router.get("/stress")
def get_stress(minutes: int = 10, db: Session = Depends(get_db)):
    data = get_recent_telemetry(db, minutes)
    dicts = [{"temperature": d.temperature, "humidity": d.humidity} for d in data]
    stress = calculate_cumulative_stress(dicts)
    return {"cumulative_stress": stress, "time_window_minutes": minutes}