"""
Singleton AnomalyDetectionService + persist detector output after each telemetry row.
"""

from __future__ import annotations

import json
from typing import Optional

from sqlalchemy.orm import Session

from models.reading import Telemetry
from services.anomaly_service import AnomalyDetectionService, anomaly_detection_constructor_kwargs
from services.detectors.base import Reading

_svc: Optional[AnomalyDetectionService] = None


def get_anomaly_service() -> AnomalyDetectionService:
    global _svc
    if _svc is None:
        _svc = AnomalyDetectionService(**anomaly_detection_constructor_kwargs())
    return _svc


def reset_anomaly_state_for_plant(plant_id: int) -> None:
    """Drop rolling windows when a plant's telemetry is cleared or deleted."""
    if plant_id:
        get_anomaly_service().reset(plant_id)


def run_detection_and_persist(db: Session, row: Telemetry) -> None:
    """Run FR10 detectors on one stored row; save events (requires plant_id)."""
    if row.plant_id is None:
        return
    svc = get_anomaly_service()
    reading = Reading(
        id=row.id,
        session_id=row.session_id or 0,
        plant_id=row.plant_id,
        timestamp=row.timestamp,
        temperature=row.temperature,
        humidity=row.humidity,
        light=int(round(row.light)) if row.light is not None else None,
        movement=row.movement,
        distance=int(round(row.distance)) if row.distance is not None else None,
    )
    events = svc.process_reading(reading)
    if not events:
        return
    for evt in events:
        db.add(
            AnomalyDetectionEvent(
                plant_id=row.plant_id,
                session_id=row.session_id,
                telemetry_id=row.id,
                created_at=evt.timestamp,
                anomaly_type=evt.anomaly_type.value,
                variable=evt.variable,
                severity=evt.severity.value,
                message=evt.message,
                detail_json=json.dumps(evt.detail) if evt.detail else None,
            )
        )
    db.commit()
