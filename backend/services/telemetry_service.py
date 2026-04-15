"""
FR1 / FR2 - Telemetry Service
Ingest, store, and query timestamped sensor readings (temperature, humidity, light).
Sampling rate: >= 1 reading/min | Resolution: temp +-0.5C, humidity +-3%RH, light +-10 lux
"""


# TODO: store_reading(session_id, temperature, humidity, light, movement, distance)
# TODO: get_readings(session_id, start_time, end_time) -> list of readings
# TODO: get_latest_reading(session_id) -> most recent reading

from sqlalchemy.orm import Session
from models.reading import Telemetry
from schemas.telemetry import TelemetryCreate
from datetime import datetime, timedelta

def create_telemetry(db: Session, data: TelemetryCreate):
    db_data = Telemetry(
        temperature=data.temperature,
        humidity=data.humidity,
        light=data.light
    )
    db.add(db_data)
    db.commit()
    db.refresh(db_data)
    return db_data

def get_telemetry_list(db: Session, skip: int = 0, limit: int = 100):
    return db.query(Telemetry).order_by(Telemetry.timestamp.desc()).offset(skip).limit(limit).all()

def get_recent_telemetry(db: Session, minutes: int = 10):
    cutoff = datetime.utcnow() - timedelta(minutes=minutes)
    return db.query(Telemetry).filter(Telemetry.timestamp >= cutoff).order_by(Telemetry.timestamp).all()