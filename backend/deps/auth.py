"""
FastAPI dependencies: current user from Bearer JWT.
"""

from typing import Annotated, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from database import get_db
from models.user import User
from services import auth_service as auth_svc

_auth_scheme = HTTPBearer(auto_error=False)


def _user_from_token(db: Session, token: Optional[str]) -> Optional[User]:
    if not token:
        return None
    uid = auth_svc.user_id_from_token(token)
    if uid is None:
        return None
    u = auth_svc.get_user_by_id(db, uid)
    if not u or not u.is_active:
        return None
    return u


def get_current_user(
    db: Annotated[Session, Depends(get_db)],
    creds: Annotated[Optional[HTTPAuthorizationCredentials], Depends(_auth_scheme)],
) -> User:
    if creds is None or not creds.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    u = _user_from_token(db, creds.credentials)
    if u is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return u


def get_current_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return user


def get_current_user_optional(
    db: Annotated[Session, Depends(get_db)],
    creds: Annotated[Optional[HTTPAuthorizationCredentials], Depends(_auth_scheme)],
) -> Optional[User]:
    if creds is None or not creds.credentials:
        return None
    return _user_from_token(db, creds.credentials)
