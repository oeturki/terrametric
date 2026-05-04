"""
Per-plant (sample) control variables: thresholds and camera options.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from deps.auth import get_current_user
from models.user import User
from schemas.control import (
    ControlProfilePayload,
    ControlResetBody,
    merge_profile_from_payload,
    validate_merged_profile,
)
from services.default_control_profile import default_control_dict
import services.plant_control_service as pc_svc
import services.plant_service as plant_svc

logger = logging.getLogger(__name__)

router = APIRouter()


def _require_owner_plant(db: Session, plant_id: int, user_id: int):
    if plant_svc.get_plant_for_owner(db, plant_id, user_id) is None:
        raise HTTPException(status_code=404, detail="Plant not found")


@router.get("")
def get_control(
    plant_id: int = Query(..., ge=1, description="Sample / plant id"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_owner_plant(db, plant_id, user.id)
    d = pc_svc.get_control_dict_for_plant(db, plant_id)
    if d is None:
        d = pc_svc.reset_to_defaults(db, plant_id)
    return d


@router.post("")
def save_control(body: ControlProfilePayload, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_owner_plant(db, body.plant_id, user.id)
    current = pc_svc.get_control_dict_for_plant(db, body.plant_id) or default_control_dict()
    merged = merge_profile_from_payload(current, body)
    try:
        validate_merged_profile(merged)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    saved = pc_svc.update_control_dict(db, body.plant_id, merged)
    try:
        from services.auto_ventilation_service import reconcile_auto_ventilation_after_profile_save

        reconcile_auto_ventilation_after_profile_save(db, body.plant_id)
    except Exception:
        logger.exception(
            "auto ventilation reconcile after save failed plant_id=%s",
            body.plant_id,
        )
    return {"status": "saved", "group": str(body.plant_id), "plant_id": body.plant_id, "controls": saved}


@router.post("/reset")
def reset_control(body: ControlResetBody, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_owner_plant(db, body.plant_id, user.id)
    saved = pc_svc.reset_to_defaults(db, body.plant_id)
    try:
        from services.auto_ventilation_service import reconcile_auto_ventilation_after_profile_save

        reconcile_auto_ventilation_after_profile_save(db, body.plant_id)
    except Exception:
        logger.exception(
            "auto ventilation reconcile after reset failed plant_id=%s",
            body.plant_id,
        )
    return {"status": "reset", "group": str(body.plant_id), "plant_id": body.plant_id, "controls": saved}
