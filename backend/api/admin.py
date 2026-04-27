"""
Minimal admin API: list users (demo / support). Cross-tenant plant/telemetry access is off
by default — extend here if you add a teacher dashboard.
"""

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from deps.auth import get_current_admin
from models.user import User
from pydantic import BaseModel

router = APIRouter()


class AdminUserRow(BaseModel):
    id: int
    email: str
    is_admin: bool
    is_active: bool

    class Config:
        from_attributes = True


@router.get("/users", response_model=List[AdminUserRow])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    rows = db.query(User).order_by(User.id).all()
    return [AdminUserRow.model_validate(r) for r in rows]
