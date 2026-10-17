"""Authentication handlers."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, EmailStr, Field

from .. import apperr, responses
from ..auth import TokenManager


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class LoginResponse(BaseModel):
    token: str
    user_id: str


def new_auth_router(tokens: TokenManager) -> APIRouter:
    """Login is a placeholder: it accepts any non-empty credentials and mints a
    token. Replace the body with a real user lookup (via a service/repository)
    when the user model lands.
    """
    router = APIRouter()

    @router.post("/auth/login")
    def login(req: LoginRequest) -> dict:
        user_id = str(uuid.uuid5(uuid.NAMESPACE_OID, str(req.email).lower()))
        try:
            token = tokens.issue(user_id)
        except Exception as exc:
            raise apperr.wrap(apperr.ERR_INTERNAL, exc) from exc
        return responses.ok(LoginResponse(token=token, user_id=user_id))

    return router
