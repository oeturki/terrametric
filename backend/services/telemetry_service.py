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
from datetime import datetime, timedelta

def get_telemetry_timeseries_data(db: Session, hours: int = 24):
    cutoff_time = datetime.utcnow() - timedelta(hours=hours)
    data = db.query(Telemetry).filter(Telemetry.timestamp >= cutoff_time).order_by(Telemetry.timestamp).all()

    timestamps = []
    temperature = []
    humidity = []
    light = []
    plant_height = []

    for item in data:
        timestamps.append(item.timestamp.isoformat())
        temperature.append(item.temperature)
        humidity.append(item.humidity)
        light.append(item.light)
        plant_height.append(item.plant_height)

    return {
        "timestamps": timestamps,
        "temperature": temperature,
        "humidity": humidity,
        "light": light,
        "plant_height": plant_height
    }