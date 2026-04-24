"""
Per-plant (sample) control variables: thresholds and camera options.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from schemas.control import (
    ControlProfilePayload,
    ControlResetBody,
    merge_profile_from_payload,
    validate_merged_profile,
)
from services.default_control_profile import default_control_dict
import services.plant_control_service as pc_svc

router = APIRouter()


@router.get("")
def get_control(plant_id: int = Query(..., ge=1, description="Sample / plant id"), db: Session = Depends(get_db)):
    pc_svc.get_plant_id_or_404(db, plant_id)
    d = pc_svc.get_control_dict_for_plant(db, plant_id)
    if d is None:
        d = pc_svc.reset_to_defaults(db, plant_id)
    return d


@router.post("")
def save_control(body: ControlProfilePayload, db: Session = Depends(get_db)):
    pc_svc.get_plant_id_or_404(db, body.plant_id)
    current = pc_svc.get_control_dict_for_plant(db, body.plant_id) or default_control_dict()
    merged = merge_profile_from_payload(current, body)
    try:
        validate_merged_profile(merged)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    saved = pc_svc.update_control_dict(db, body.plant_id, merged)
    return {"status": "saved", "group": str(body.plant_id), "plant_id": body.plant_id, "controls": saved}


@router.post("/reset")
def reset_control(body: ControlResetBody, db: Session = Depends(get_db)):
    pc_svc.get_plant_id_or_404(db, body.plant_id)
    saved = pc_svc.reset_to_defaults(db, body.plant_id)
    return {"status": "reset", "group": str(body.plant_id), "plant_id": body.plant_id, "controls": saved}
