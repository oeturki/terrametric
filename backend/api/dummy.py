"""
Dummy data utilities (Phase 2).

A small router exposing one endpoint for now: backfill historical telemetry
for a plant so the UI can be exercised without an Arduino. Kept separate
from /api/telemetry/ingest so the real ingest path stays a single-purpose
contract that the Arduino sketch posts to.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as OrmSession

from database import get_db
from deps.auth import get_current_user
from models.audit_log import AuditLog
from models.user import User
from schemas.session_schema import ScenarioName
from services import dummy_stream
from services.plant_service import get_plant_for_owner

router = APIRouter()


class BackfillRequest(BaseModel):
    plant_id: int
    hours: int = Field(24, ge=1, le=720)
    scenario: ScenarioName = "stable"
    interval_sec: int = Field(60, ge=5, le=3600)


class BackfillResponse(BaseModel):
    plant_id: int
    rows_inserted: int
    scenario: str
    hours: int
    interval_sec: int


@router.post("/backfill", response_model=BackfillResponse)
def backfill(
    body: BackfillRequest,
    db: OrmSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Generate ``hours`` of synthetic telemetry stamped to ``plant_id``.
    Rows are inserted in one bulk transaction; audit log captures the request
    so it's clear during analysis which rows came from a simulator.
    """
    if get_plant_for_owner(db, body.plant_id, user.id) is None:
        raise HTTPException(status_code=404, detail="Plant not found")

    rows = dummy_stream.backfill_history(
        db,
        plant_id=body.plant_id,
        hours=body.hours,
        scenario=body.scenario,
        interval_sec=body.interval_sec,
    )
    db.add(
        AuditLog(
            entity_type="plant",
            entity_id=body.plant_id,
            action="backfill_dummy",
            user_id=user.id,
            payload_json=json.dumps({
                "rows": rows,
                "scenario": body.scenario,
                "hours": body.hours,
                "interval_sec": body.interval_sec,
            }),
        )
    )
    db.commit()

    return BackfillResponse(
        plant_id=body.plant_id,
        rows_inserted=rows,
        scenario=body.scenario,
        hours=body.hours,
        interval_sec=body.interval_sec,
    )
