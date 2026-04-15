"""
FR10 - Anomaly Detection endpoints.  [Owner: Omer]

Provides REST API for querying detected anomalies and running simulations.
The simulate endpoint lets you test the full detection pipeline without
real sensors -- it generates fake data, runs it through the detectors,
and returns the results in the same shape the Terrametric UI expects.
"""

from __future__ import annotations

import sys
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.anomaly_service import AnomalyDetectionService, Reading, AnomalyEvent
from services.detectors.base import SENSOR_PROFILES
from simulation.simulator import (
    generate_stable_series,
    inject_drift,
    inject_noise,
    inject_gap,
)

router = APIRouter()

# In-memory store -- replaced by DB in production
_event_store: list[dict] = []
_service = AnomalyDetectionService(
    drift_window=10,
    noise_window=10,
    dropout_multiplier=3,
    dropout_baseline_count=5,
)

SEVERITY_MAP = {
    "critical": "danger",
    "warning": "warning",
    "info": "info",
}


def _event_to_ui(evt: AnomalyEvent) -> dict:
    """Convert an AnomalyEvent to the JSON shape the Terrametric UI expects."""
    return {
        "timestamp": evt.timestamp.isoformat(),
        "sensor": evt.variable,
        "description": evt.message,
        "severity": SEVERITY_MAP.get(evt.severity.value, evt.severity.value),
        "status": "active",
        "type": evt.anomaly_type.value,
    }


def _build_summary(events: list[dict]) -> dict:
    """Build the summary object the UI's fetchAnomalies() expects."""
    noise_count = sum(1 for e in events if e.get("type") == "noise")
    dropout_count = sum(1 for e in events if e.get("type") == "dropout")
    drift_count = sum(1 for e in events if e.get("type") == "drift")
    return {
        "spikes": noise_count,
        "missing": dropout_count,
        "drift": drift_count,
        "total": len(events),
        "events": events,
    }


@router.get("")
def list_anomalies(
    session_id: Optional[int] = Query(None),
    anomaly_type: Optional[str] = Query(None),
    variable: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
):
    """
    GET /api/anomalies
    Returns anomaly events in the shape the Terrametric UI expects.
    Filterable by session_id, anomaly_type, variable, severity.
    """
    filtered = _event_store

    if session_id is not None:
        filtered = [e for e in filtered if e.get("session_id") == session_id]
    if anomaly_type:
        filtered = [e for e in filtered if e.get("type") == anomaly_type]
    if variable:
        filtered = [e for e in filtered if e.get("sensor") == variable]
    if severity:
        filtered = [e for e in filtered if e.get("severity") == severity]

    ui_events = [{k: v for k, v in e.items() if k != "session_id"} for e in filtered]
    return _build_summary(ui_events)


@router.get("/summary/{session_id}")
def anomaly_summary(session_id: int):
    """
    GET /api/anomalies/summary/{session_id}
    Returns anomaly summary for a specific session.
    """
    session_events = [e for e in _event_store if e.get("session_id") == session_id]
    return _build_summary(session_events)


@router.post("/simulate")
def simulate_anomalies(
    scenario: str = Query("drift", description="One of: stable, drift, noise, dropout, all"),
    duration_min: int = Query(30, description="Duration of simulated data in minutes"),
):
    """
    POST /api/anomalies/simulate?scenario=drift
    Generates synthetic data, runs it through the anomaly detectors,
    and returns readings + detected events for the Terrametric UI.

    Scenarios:
      stable  -- normal data, should produce 0 anomalies
      drift   -- temperature gradually increases
      noise   -- temperature becomes very jittery
      dropout -- 8-minute gap in the middle of the data
      all     -- drift + noise + dropout combined
    """
    global _event_store

    # Reset the service so each simulation starts fresh
    _service.reset(session_id=99)

    seed = 42
    series = generate_stable_series(
        duration_min=duration_min,
        interval_sec=60,
        seed=seed,
        noise_std={"temperature": 0.1, "humidity": 0.5, "light": 5.0},
    )

    if scenario == "drift" or scenario == "all":
        series = inject_drift(series, "temperature", slope_per_reading=0.15)
    if scenario == "noise" or scenario == "all":
        start = len(series) // 2
        series = inject_noise(series, "temperature", noise_std=4.0, start_index=start, seed=123)
    if scenario == "dropout" or scenario == "all":
        gap_start = len(series) // 3
        series = inject_gap(series, start_index=gap_start, gap_count=8)

    # Run each reading through the detection pipeline
    all_events: list[dict] = []
    readings_out: list[dict] = []

    for d in series:
        reading = Reading(
            session_id=99,
            timestamp=datetime.fromisoformat(d["timestamp"]),
            temperature=d.get("temperature"),
            humidity=d.get("humidity"),
            light=d.get("light"),
            movement=d.get("movement"),
            distance=d.get("distance"),
        )

        events = _service.process_reading(reading)

        reading_dict = {
            "timestamp": d["timestamp"],
            "temperature": d.get("temperature"),
            "humidity": d.get("humidity"),
            "light": d.get("light"),
            "height": d.get("distance"),
        }
        readings_out.append(reading_dict)

        for evt in events:
            ui_evt = _event_to_ui(evt)
            ui_evt["session_id"] = 99
            all_events.append(ui_evt)

    # Store events for GET /api/anomalies to return
    _event_store = all_events

    summary = _build_summary(
        [{k: v for k, v in e.items() if k != "session_id"} for e in all_events]
    )

    return {
        "scenario": scenario,
        "readings_count": len(readings_out),
        "readings": readings_out,
        **summary,
    }


@router.delete("/clear")
def clear_anomalies():
    """Clear the in-memory event store."""
    global _event_store
    _event_store = []
    _service.reset(session_id=99)
    return {"status": "cleared"}
