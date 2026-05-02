"""Batch ML anomaly-type classification over stored telemetry windows."""

from __future__ import annotations

from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from deps.auth import get_current_user
from models.user import User
from services.ml_classifier_service import classify_plant_window
from services.plant_service import get_plant_for_owner


router = APIRouter()


class ClassifyWindowPayload(BaseModel):
    plant_id: int = Field(..., ge=1)
    hours: int = Field(24, ge=1, le=720)
    persist: bool = False


@router.post("/classify/window")
def post_classify_window(
    payload: ClassifyWindowPayload,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if get_plant_for_owner(db, payload.plant_id, user.id) is None:
        raise HTTPException(status_code=404, detail="Plant not found")
    return classify_plant_window(db, plant_id=payload.plant_id, hours=payload.hours, persist=payload.persist)

