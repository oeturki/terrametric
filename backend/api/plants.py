"""
FR7 — Plants (samples / trays).

JSON shape matches existing frontend/static JS: loc, germ, qr (plus id, name, notes).
All routes require authentication; each user sees only plants they own.
"""

from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session as OrmSession

from database import get_db
from deps.auth import get_current_user
from models.plant import Plant
from models.user import User
from schemas.plant import PlantCreate, PlantUpdate
import services.plant_service as plant_svc
from services.telemetry_service import get_telemetry_timeseries_data

router = APIRouter()


def _plant_tray_dict(p: Plant) -> dict[str, Any]:
    """Map ORM plant to the tray object `frontend/js/api.js` expects."""
    return {
        "id": p.id,
        "name": p.name or "",
        "loc": p.location or "",
        "germ": p.germination_date.isoformat() if p.germination_date else "",
        "notes": p.notes or "",
        "qr": p.qr_code or "",
        "species": p.species,
        "genotype": p.genotype,
        "treatment_group": p.treatment_group,
        "lifecycle_state": p.lifecycle_state,
    }


@router.get("")
def list_plants(
    db: OrmSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[dict[str, Any]]:
    return [_plant_tray_dict(p) for p in plant_svc.list_plants(db, owner_id=user.id)]


@router.post("")
def create_plant(
    body: PlantCreate,
    db: OrmSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    if body.qr_code:
        existing = plant_svc.get_plant_by_qr_for_owner(db, body.qr_code, user.id)
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail=f"A sample with QR '{body.qr_code}' already exists in your account (id={existing.id}).",
            )
    p = plant_svc.create_plant(db, body, user_id=user.id)
    return _plant_tray_dict(p)


@router.delete("")
def delete_all_plants(
    confirm: str = Query("", description="Must equal 'DELETE' to authorise the bulk wipe."),
    db: OrmSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if confirm != "DELETE":
        raise HTTPException(
            status_code=400,
            detail="Bulk delete requires ?confirm=DELETE to acknowledge the destructive action.",
        )
    removed = plant_svc.delete_all_plants(db, user_id=user.id)
    return {"removed": removed}


@router.get("/qr/{qr}")
def get_by_qr(qr: str, db: OrmSession = Depends(get_db), user: User = Depends(get_current_user)):
    p = plant_svc.get_plant_by_qr_for_owner(db, qr, user.id)
    if not p:
        raise HTTPException(status_code=404, detail="Plant not found for QR")
    return _plant_tray_dict(p)


@router.get("/{plant_id}/timeseries")
def plant_timeseries(
    plant_id: int,
    hours: int = Query(24, ge=1, le=8760),
    db: OrmSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if plant_svc.get_plant_for_owner(db, plant_id, user.id) is None:
        raise HTTPException(status_code=404, detail="Plant not found")
    return get_telemetry_timeseries_data(db, hours=hours, plant_id=plant_id)


@router.get("/{plant_id}")
def get_plant(plant_id: int, db: OrmSession = Depends(get_db), user: User = Depends(get_current_user)):
    p = plant_svc.get_plant_for_owner(db, plant_id, user.id)
    if not p:
        raise HTTPException(status_code=404, detail="Plant not found")
    return _plant_tray_dict(p)


@router.put("/{plant_id}")
def update_plant(
    plant_id: int,
    body: PlantUpdate,
    db: OrmSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        p = plant_svc.update_plant(db, plant_id, body, user_id=user.id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    if not p:
        raise HTTPException(status_code=404, detail="Plant not found")
    return _plant_tray_dict(p)


@router.delete("/{plant_id}", status_code=204)
def delete_plant(plant_id: int, db: OrmSession = Depends(get_db), user: User = Depends(get_current_user)):
    if not plant_svc.delete_plant(db, plant_id, user_id=user.id):
        raise HTTPException(status_code=404, detail="Plant not found")


@router.delete("/{plant_id}/telemetry")
def clear_plant_telemetry(plant_id: int, db: OrmSession = Depends(get_db), user: User = Depends(get_current_user)):
    rows_deleted = plant_svc.clear_telemetry_for_plant(db, plant_id, user_id=user.id)
    if rows_deleted is None:
        raise HTTPException(status_code=404, detail="Plant not found")
    return {"plant_id": plant_id, "rows_deleted": rows_deleted}
