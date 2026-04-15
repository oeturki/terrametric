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
    inject_spike,
    inject_level_shift,
    inject_correlation_break,
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
        "detail": evt.detail,
    }


def _build_summary(events: list[dict]) -> dict:
    """Build the summary object the UI expects, covering all detector types."""
    by_type: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for e in events:
        t = e.get("type", "unknown")
        s = e.get("severity", "info")
        by_type[t] = by_type.get(t, 0) + 1
        by_severity[s] = by_severity.get(s, 0) + 1

    return {
        "total": len(events),
        "by_type": by_type,
        "by_severity": by_severity,
        "spike": by_type.get("spike", 0),
        "drift": by_type.get("drift", 0),
        "noise": by_type.get("noise", 0),
        "dropout": by_type.get("dropout", 0),
        "correlation": by_type.get("correlation", 0),
        "level_shift": by_type.get("level_shift", 0),
        "ewma_breach": by_type.get("ewma_breach", 0),
        "seasonal": by_type.get("seasonal", 0),
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
    scenario: str = Query(
        "drift",
        description="One of: stable, drift, noise, dropout, spike, "
                    "level_shift, correlation, all",
    ),
    duration_min: int = Query(30, description="Duration of simulated data in minutes"),
):
    """
    POST /api/anomalies/simulate?scenario=drift

    Scenarios:
      stable      -- normal data, should produce 0 anomalies
      drift       -- temperature gradually increases
      noise       -- temperature becomes very jittery
      dropout     -- 8-minute gap in the middle of the data
      spike       -- random sensor spikes injected
      level_shift -- abrupt step change mid-way through
      correlation -- break temp/humidity physical correlation
      all         -- every injection combined
    """
    global _event_store
    _service.reset(session_id=99)

    seed = 42
    series = generate_stable_series(
        duration_min=duration_min,
        interval_sec=60,
        seed=seed,
        noise_std={"temperature": 0.1, "humidity": 0.5, "light": 5.0},
    )

    sc = scenario
    if sc in ("drift", "all"):
        series = inject_drift(series, "temperature", slope_per_reading=0.15)
    if sc in ("noise", "all"):
        start = len(series) // 2
        series = inject_noise(series, "temperature", noise_std=4.0, start_index=start, seed=123)
    if sc in ("dropout", "all"):
        gap_start = len(series) // 3
        series = inject_gap(series, start_index=gap_start, gap_count=8)
    if sc in ("spike", "all"):
        series = inject_spike(series, "temperature", count=3, magnitude=15.0, seed=seed)
    if sc in ("level_shift", "all"):
        series = inject_level_shift(series, "temperature", shift_amount=8.0)
    if sc in ("correlation", "all"):
        series = inject_correlation_break(series, seed=seed)

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

        readings_out.append({
            "timestamp": d["timestamp"],
            "temperature": d.get("temperature"),
            "humidity": d.get("humidity"),
            "light": d.get("light"),
            "height": d.get("distance"),
        })

        for evt in events:
            ui_evt = _event_to_ui(evt)
            ui_evt["session_id"] = 99
            all_events.append(ui_evt)

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
