"""
Load / save per-plant control JSON in ``plant_control`` table.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from models.plant import Plant
from models.plant_control import PlantControl
from services.default_control_profile import default_control_dict, default_control_json
from services.plant_service import get_plant


def get_plant_id_or_404(db: Session, plant_id: int) -> Plant:
    from fastapi import HTTPException

    p = get_plant(db, plant_id)
    if not p:
        raise HTTPException(status_code=404, detail="Plant not found")
    return p


def get_control_dict_for_plant(db: Session, plant_id: int) -> Optional[Dict[str, Any]]:
    row = db.query(PlantControl).filter(PlantControl.plant_id == plant_id).first()
    if not row:
        return None
    return json.loads(row.profile_json)


def update_control_dict(db: Session, plant_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    s = json.dumps(data)
    row = db.query(PlantControl).filter(PlantControl.plant_id == plant_id).first()
    if not row:
        row = PlantControl(plant_id=plant_id, profile_json=s)
        db.add(row)
    else:
        row.profile_json = s
    db.commit()
    return json.loads(row.profile_json)


def reset_to_defaults(db: Session, plant_id: int) -> Dict[str, Any]:
    d = default_control_dict()
    return update_control_dict(db, plant_id, d)
