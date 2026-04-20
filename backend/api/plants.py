"""
FR7 — Plants (samples / trays).

JSON shape matches existing frontend/static JS: loc, germ, qr (plus id, name, notes).
"""

from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session as OrmSession

from database import get_db
from models.plant import Plant
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
def list_plants(db: OrmSession = Depends(get_db)) -> List[dict[str, Any]]:
    return [_plant_tray_dict(p) for p in plant_svc.list_plants(db)]


@router.post("")
def create_plant(body: PlantCreate, db: OrmSession = Depends(get_db)) -> dict[str, Any]:
    # Catch the QR-uniqueness collision early so the client gets 409 not 500.
    if body.qr_code:
        existing = plant_svc.get_plant_by_qr(db, body.qr_code)
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail=f"A sample with QR '{body.qr_code}' already exists (id={existing.id}).",
            )
    p = plant_svc.create_plant(db, body)
    return _plant_tray_dict(p)


@router.delete("")
def delete_all_plants(
    confirm: str = Query("", description="Must equal 'DELETE' to authorise the bulk wipe."),
    db: OrmSession = Depends(get_db),
):
    """
    Cascading delete every plant + their telemetry + their recording sessions.
    Guarded by a literal ?confirm=DELETE token so accidental clicks at the API layer
    cannot wipe the dataset.
    """
    if confirm != "DELETE":
        raise HTTPException(
            status_code=400,
            detail="Bulk delete requires ?confirm=DELETE to acknowledge the destructive action.",
        )
    removed = plant_svc.delete_all_plants(db)
    return {"removed": removed}


@router.get("/qr/{qr}")
def get_by_qr(qr: str, db: OrmSession = Depends(get_db)) -> dict[str, Any]:
    p = plant_svc.get_plant_by_qr(db, qr)
    if not p:
        raise HTTPException(status_code=404, detail="Plant not found for QR")
    return _plant_tray_dict(p)


@router.get("/{plant_id}/timeseries")
def plant_timeseries(
    plant_id: int,
    hours: int = Query(24, ge=1, le=8760),
    db: OrmSession = Depends(get_db),
):
    if plant_svc.get_plant(db, plant_id) is None:
        raise HTTPException(status_code=404, detail="Plant not found")
    return get_telemetry_timeseries_data(db, hours=hours, plant_id=plant_id)


@router.get("/{plant_id}")
def get_plant(plant_id: int, db: OrmSession = Depends(get_db)) -> dict[str, Any]:
    p = plant_svc.get_plant(db, plant_id)
    if not p:
        raise HTTPException(status_code=404, detail="Plant not found")
    return _plant_tray_dict(p)


@router.put("/{plant_id}")
def update_plant(plant_id: int, body: PlantUpdate, db: OrmSession = Depends(get_db)) -> dict[str, Any]:
    p = plant_svc.update_plant(db, plant_id, body)
    if not p:
        raise HTTPException(status_code=404, detail="Plant not found")
    return _plant_tray_dict(p)


@router.delete("/{plant_id}", status_code=204)
def delete_plant(plant_id: int, db: OrmSession = Depends(get_db)):
    if not plant_svc.delete_plant(db, plant_id):
        raise HTTPException(status_code=404, detail="Plant not found")


@router.delete("/{plant_id}/telemetry")
def clear_plant_telemetry(plant_id: int, db: OrmSession = Depends(get_db)):
    """
    Wipe telemetry for one sample without deleting the sample record itself.
    Stops any active recording session for the plant first to avoid an immediate refill.
    """
    rows_deleted = plant_svc.clear_telemetry_for_plant(db, plant_id)
    if rows_deleted is None:
        raise HTTPException(status_code=404, detail="Plant not found")
    return {"plant_id": plant_id, "rows_deleted": rows_deleted}
