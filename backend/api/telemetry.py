"""
FR1 / FR2 - Environmental Monitoring & Data Logging endpoints.
Ingest sensor readings, query time-series data.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta

app = FastAPI(title="TerraMetric Telemetry Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def generate_time_series_dataset(data_points: int = 50):
    data = []
    start_time = datetime.now() - timedelta(hours=data_points)

    for i in range(data_points):
        timestamp = start_time + timedelta(hours=i)
        data.append({
            "timestamp": timestamp.isoformat(),
            "temperature": round(18 + (i % 14), 2),
            "humidity": round(40 + (i % 45), 2),
            "light": round(50 + (i % 1450), 2),
            "plant_height": round(10 + (i % 30), 2)
        })
    return data

@app.get("/api/telemetry/history")
def get_telemetry_history():
    return generate_time_series_dataset()