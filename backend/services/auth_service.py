"""
Password hashing and JWT creation for API auth.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from config import settings
from models.user import User


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(*, user_id: int, email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


def user_id_from_token(token: str) -> Optional[int]:
    try:
        data = decode_token(token)
        sub = data.get("sub")
        if sub is None:
            return None
        return int(sub)
    except (JWTError, ValueError, TypeError):
        return None


def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    norm = email.strip().lower()
    return db.query(User).filter(User.email == norm).first()

def create_user(db: Session, email: str, password: str, *, is_admin: bool = False) -> User:
    norm = email.strip().lower()

    existing = get_user_by_email(db, norm)
    if existing:
        raise ValueError("user_already_exists")  # or just return existing

    u = User(
        email=norm,
        password_hash=hash_password(password),
        is_admin=is_admin,
        is_active=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u

def authenticate(db: Session, email: str, password: str) -> Optional[User]:
    u = get_user_by_email(db, email)
    if not u or not u.is_active:
        return None
    if not verify_password(password, u.password_hash):
        return None
    return u
