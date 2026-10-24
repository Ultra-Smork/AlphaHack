"""Email/password authentication handlers."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import apperr, responses
from ..auth import TokenManager, verify_password
from ..middleware.auth import get_user_id
from ..models import User
from ..platform.db import get_db
from ..schemas import LoginRequest, LoginResponse


def new_auth_router(tokens: TokenManager) -> APIRouter:
    router = APIRouter()

    @router.post("/auth/login")
    def login(req: LoginRequest, db: Session = Depends(get_db)) -> dict:
        user = db.scalar(select(User).where(User.email == req.email))
        if user is None or not verify_password(req.password, user.password_hash):
            raise apperr.new(
                401, "invalid_credentials", "invalid email or password"
            )

        token = tokens.issue(str(user.id), user.role)
        return responses.ok(LoginResponse(access_token=token))

    return router


def get_current_user(
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
) -> User:
    try:
        uid = int(user_id)
    except (TypeError, ValueError) as exc:
        raise apperr.ERR_INVALID_TOKEN from exc

    user = db.get(User, uid)
    if user is None:
        raise apperr.ERR_INVALID_TOKEN
    return user
