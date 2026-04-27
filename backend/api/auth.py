"""
Registration, login, JWT; admin registration when ``ADMIN_REGISTRATION_SECRET`` is configured.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from deps.auth import get_current_user
from models.user import User
from schemas.auth import LoginIn, RegisterAdminIn, RegisterIn, TokenOut, UserOut
from services import auth_service as auth_svc

router = APIRouter()


@router.post("/register", response_model=TokenOut)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if auth_svc.get_user_by_email(db, body.email):
        raise HTTPException(status_code=409, detail="Email already registered")
    u = auth_svc.create_user(db, body.email, body.password, is_admin=False)
    tok = auth_svc.create_access_token(user_id=u.id, email=u.email)
    return TokenOut(access_token=tok)


@router.post("/register-admin", response_model=TokenOut)
def register_admin(body: RegisterAdminIn, db: Session = Depends(get_db)):
    if settings.ADMIN_REGISTRATION_SECRET and body.admin_secret != settings.ADMIN_REGISTRATION_SECRET:
        raise HTTPException(status_code=403, detail="Invalid admin registration secret")
    if auth_svc.get_user_by_email(db, body.email):
        raise HTTPException(status_code=409, detail="Email already registered")
    u = auth_svc.create_user(db, body.email, body.password, is_admin=True)
    tok = auth_svc.create_access_token(user_id=u.id, email=u.email)
    return TokenOut(access_token=tok)


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    u = auth_svc.authenticate(db, body.email, body.password)
    if not u:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    tok = auth_svc.create_access_token(user_id=u.id, email=u.email)
    return TokenOut(access_token=tok)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)
