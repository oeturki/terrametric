"""
Group 14 IoT Greenhouse Backend
Entry point for the FastAPI application.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import telemetry, alerts, control, camera, auth, plants, sessions, reports, anomalies

app = FastAPI(
    title="Group 14 - Environmental Control & Research Integrity System",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(anomalies.router,  prefix="/api/anomalies",  tags=["Anomaly Detection"])
app.include_router(auth.router,       prefix="/api/auth",       tags=["Authentication"])
app.include_router(telemetry.router,  prefix="/api/telemetry",  tags=["Telemetry"])
app.include_router(alerts.router,     prefix="/api/alerts",     tags=["Alerts"])
app.include_router(control.router,    prefix="/api/control",    tags=["Control"])
app.include_router(camera.router,     prefix="/api/camera",     tags=["Camera"])
app.include_router(plants.router,     prefix="/api/plants",     tags=["Plants"])
app.include_router(sessions.router,   prefix="/api/sessions",   tags=["Sessions"])
app.include_router(reports.router,    prefix="/api/reports",     tags=["Reports"])


@app.get("/health")
def health_check():
    return {"status": "ok"}
