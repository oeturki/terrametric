"""
Group 14 IoT Greenhouse Backend
Entry point for the FastAPI application.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api import (
    telemetry, alerts, control, camera, auth, plants, sessions, reports, anomalies, devices,
    dummy,
)
from database import Base, engine, run_sqlite_migrations
from services.dummy_stream import supervisor as stream_supervisor

# Import models so SQLAlchemy registers all tables on Base.metadata
import models  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio as _asyncio

    Base.metadata.create_all(bind=engine)
    run_sqlite_migrations(engine)
    # Hand the supervisor the loop so sync API handlers running in worker
    # threads can still create/cancel asyncio tasks safely.
    stream_supervisor.bind_loop(_asyncio.get_running_loop())
    try:
        yield
    finally:
        # Cancel any running dummy-data streamers so the process can exit cleanly.
        await stream_supervisor.stop_all()

# Static TerraMetric UI (frontend/index.html + js/ + css/) — same origin as /api/*
_BACKEND_DIR = Path(__file__).resolve().parent
_FRONTEND_DIR = _BACKEND_DIR.parent / "frontend"

app = FastAPI(
    title="Group 14 - Environmental Control & Research Integrity System",
    version="0.1.0",
    lifespan=lifespan,
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
app.include_router(devices.router,    prefix="/api/devices",    tags=["Devices"])
app.include_router(sessions.router,   prefix="/api/sessions",   tags=["Sessions"])
app.include_router(reports.router,    prefix="/api/reports",     tags=["Reports"])
app.include_router(dummy.router,      prefix="/api/dummy",       tags=["Dummy data"])


@app.get("/health")
def health_check():
    return {"status": "ok"}


# Mount last: serves frontend/index.html at / and /index.html, plus /js/*, /css/* (one uvicorn = full app).
if _FRONTEND_DIR.is_dir():
    app.mount(
        "/",
        StaticFiles(directory=str(_FRONTEND_DIR), html=True),
        name="frontend",
    )
