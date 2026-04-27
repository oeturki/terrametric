"""
Auth request/response shapes.
"""

from pydantic import BaseModel, EmailStr, Field


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: str
    is_admin: bool

    class Config:
        from_attributes = True


class RegisterAdminIn(RegisterIn):
    """Same as register plus a shared secret when ``ADMIN_REGISTRATION_SECRET`` is set."""

    admin_secret: str = ""
