"""
JWT authentication middleware.
Verifies Bearer tokens on protected routes and injects the current user.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


# TODO: decode_token(token: str) -> dict  (verify JWT, return payload)
# TODO: get_current_user(token = Depends(oauth2_scheme)) -> User
# TODO: require_active_user(user = Depends(get_current_user)) -> User (check is_active)
