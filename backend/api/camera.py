"""
FR5 — Gallery: persisted Pi camera JPEGs per plant (sample).
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from database import get_db
from deps.auth import get_current_user
from models.plant import Plant
from models.user import User
from services import camera_service as cam_svc

router = APIRouter()


def _owner_plant_ids(db: Session, user_id: int) -> List[int]:
    return [r[0] for r in db.query(Plant.id).filter(Plant.owner_id == user_id).all()]


@router.get("/images")
def list_images(
    plant_id: Optional[int] = Query(None, ge=1, description="Filter to one sample owned by you"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    mine = _owner_plant_ids(db, user.id)
    if plant_id is not None and plant_id not in mine:
        raise HTTPException(status_code=403, detail="Sample not yours")
    data = cam_svc.list_captures_json_for_plants(db, mine, plant_id_filter=plant_id)
    return data


@router.delete("/images", status_code=200)
def delete_all_images_for_plant(
    plant_id: int = Query(..., ge=1, description="Delete every gallery capture for this sample"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    mine = _owner_plant_ids(db, user.id)
    if plant_id not in mine:
        raise HTTPException(status_code=403, detail="Sample not yours")
    ok, deleted = cam_svc.delete_all_captures_for_plant(db, plant_id, user.id)
    if not ok:
        raise HTTPException(status_code=403, detail="Sample not yours")
    return {"deleted": deleted}


@router.delete("/images/{capture_id}", status_code=204)
def delete_one_image(
    capture_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    gone = cam_svc.delete_capture_for_owner(db, capture_id, user.id)
    if not gone:
        raise HTTPException(status_code=404, detail="Image not found")
    return Response(status_code=204)


@router.get("/images/{capture_id}/file")
def get_image_file(
    capture_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    cap = cam_svc.get_capture_for_owner(db, capture_id, user.id)
    if cap is None:
        raise HTTPException(status_code=404, detail="Image not found")
    try:
        path = cam_svc.absolute_file_path(cap)
    except ValueError:
        raise HTTPException(status_code=404, detail="Bad path") from None
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Missing file")
    return FileResponse(str(path), media_type="image/jpeg", filename=f"capture_{capture_id}.jpg")

