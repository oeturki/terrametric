"""
FR10 - Anomaly Detection endpoints.

Live/dummy ingest: events persisted in ``anomaly_detection_events`` (see ``anomaly_runtime``).

Lab: POST /simulate generates synthetic series in-process only (no DB writes) for teaching/demo.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from deps.auth import get_current_user
from models.anomaly_detection_event import AnomalyDetectionEvent
from models.plant import Plant
from models.reading import Telemetry
from models.user import User

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.anomaly_runtime import get_anomaly_service, reset_anomaly_state_for_plant, run_detection_and_persist
from services.anomaly_service import AnomalyEvent
from services.detectors.base import Reading
from services.plant_service import get_plant_for_owner
from simulation.simulator import (
    generate_stable_series,
    inject_correlation_break,
    inject_drift,
    inject_gap,
    inject_level_shift,
    inject_noise,
    inject_spike,
)

router = APIRouter()

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


def _db_row_to_ui(r: AnomalyDetectionEvent) -> dict:
    detail: dict[str, Any] = {}
    if r.detail_json:
        try:
            detail = json.loads(r.detail_json)
        except json.JSONDecodeError:
            detail = {}
    return {
        "id": r.id,
        "timestamp": r.created_at.isoformat(),
        "sensor": r.variable,
        "description": r.message or "",
        "severity": SEVERITY_MAP.get(r.severity, r.severity),
        "status": "active",
        "type": r.anomaly_type,
        "detail": detail,
        "plant_id": r.plant_id,
        "session_id": r.session_id,
        "telemetry_id": r.telemetry_id,
        "source": "live",
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


def _scoped_anomaly_query(
    db: Session,
    user: User,
    *,
    plant_id: Optional[int],
    session_id: Optional[int],
    hours: Optional[int],
    anomaly_type: Optional[str],
    variable: Optional[str],
    severity: Optional[str],
):
    q = (
        db.query(AnomalyDetectionEvent)
        .join(Plant, Plant.id == AnomalyDetectionEvent.plant_id)
        .filter(Plant.owner_id == user.id)
    )
    if plant_id is not None:
        q = q.filter(AnomalyDetectionEvent.plant_id == plant_id)
    if session_id is not None:
        q = q.filter(AnomalyDetectionEvent.session_id == session_id)
    if hours is not None and hours > 0:
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        q = q.filter(AnomalyDetectionEvent.created_at >= cutoff)
    rows = q.order_by(AnomalyDetectionEvent.created_at.desc()).limit(2000).all()
    out: List[dict] = []
    for r in rows:
        d = _db_row_to_ui(r)
        if anomaly_type and d.get("type") != anomaly_type:
            continue
        if variable and d.get("sensor") != variable:
            continue
        if severity and d.get("severity") != severity:
            continue
        out.append(d)
    return out


@router.get("")
def list_anomalies(
    session_id: Optional[int] = Query(None),
    plant_id: Optional[int] = Query(None),
    hours: Optional[int] = Query(None, ge=1, le=8760, description="Only events newer than N hours"),
    anomaly_type: Optional[str] = Query(None),
    variable: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Persisted detector events for your samples (from live/dummy ingest).
    """
    events = _scoped_anomaly_query(
        db,
        user,
        plant_id=plant_id,
        session_id=session_id,
        hours=hours,
        anomaly_type=anomaly_type,
        variable=variable,
        severity=severity,
    )
    return _build_summary(events)


@router.get("/summary/{session_id}")
def anomaly_summary(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    events = _scoped_anomaly_query(
        db, user, plant_id=None, session_id=session_id, hours=None,
        anomaly_type=None, variable=None, severity=None,
    )
    return _build_summary(events)


@router.post("/simulate")
def simulate_anomalies(
    scenario: str = Query(
        "drift",
        description="One of: stable, drift, noise, dropout, spike, "
        "level_shift, correlation, all",
    ),
    duration_min: int = Query(30, description="Duration of simulated data in minutes"),
    _: User = Depends(get_current_user),
):
    """
    Synthetic lab only: does **not** write telemetry or anomaly rows to the database.
    """
    lab_key = 99
    svc = get_anomaly_service()
    svc.reset(lab_key)

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
            session_id=lab_key,
            plant_id=None,
            timestamp=datetime.fromisoformat(d["timestamp"]),
            temperature=d.get("temperature"),
            humidity=d.get("humidity"),
            light=d.get("light"),
            movement=d.get("movement"),
            distance=d.get("distance"),
        )

        events = svc.process_reading(reading)

        readings_out.append({
            "timestamp": d["timestamp"],
            "temperature": d.get("temperature"),
            "humidity": d.get("humidity"),
            "light": d.get("light"),
            "height": d.get("distance"),
        })

        for evt in events:
            ui_evt = _event_to_ui(evt)
            ui_evt["session_id"] = lab_key
            ui_evt["source"] = "synthetic_lab"
            all_events.append(ui_evt)

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
def clear_anomalies_lab(_: User = Depends(get_current_user)):
    """Reset only the synthetic-lab detector state (session key 99). Does not delete DB events."""
    get_anomaly_service().reset(99)
    return {"status": "cleared", "scope": "synthetic_lab_session_only"}


@router.post("/reprocess")
def reprocess_anomalies(
    plant_id: int = Query(..., ge=1),
    hours: int = Query(24, ge=1, le=720),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Replay telemetry for a sample through detectors and repopulate persisted events
    for that window (useful after code changes or to backfill).
    """
    if get_plant_for_owner(db, plant_id, user.id) is None:
        raise HTTPException(status_code=404, detail="Plant not found")
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    db.query(AnomalyDetectionEvent).filter(
        AnomalyDetectionEvent.plant_id == plant_id,
        AnomalyDetectionEvent.created_at >= cutoff,
    ).delete(synchronize_session=False)
    db.commit()

    reset_anomaly_state_for_plant(plant_id)

    rows = (
        db.query(Telemetry)
        .filter(Telemetry.plant_id == plant_id, Telemetry.timestamp >= cutoff)
        .order_by(Telemetry.timestamp.asc())
        .all()
    )
    n = 0
    for row in rows:
        run_detection_and_persist(db, row)
        n += 1
    return {"plant_id": plant_id, "telemetry_rows_reprocessed": n, "hours": hours}
