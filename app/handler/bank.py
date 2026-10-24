"""Bank queue and manual-review endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session

from .. import responses
from ..models import User
from ..platform.db import get_db
from ..schemas import ReviewRequest
from ..services import application_service as service
from .auth import get_current_user

router = APIRouter()


@router.get("/bank/applications")
def bank_queue(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    items = service.bank_queue(db, user)
    return responses.ok([item.model_dump(mode="json") for item in items])


@router.post("/bank/applications/{application_id}/review")
def review_application(
    application_id: int,
    payload: ReviewRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    key = _key(idempotency_key)
    request_hash = (
        service.make_request_hash(
            request.method,
            request.url.path,
            payload.model_dump(mode="json"),
        )
        if key
        else ""
    )
    if key:
        cached = service.get_idempotent_response(db, key, request_hash)
        if cached is not None:
            return responses.ok(cached)

    result = service.review_application(
        db,
        user,
        application_id,
        payload.decision,
        payload.reason,
    )
    body = result.model_dump(mode="json")
    if key:
        service.save_idempotent_response(db, key, request_hash, body)
    return responses.ok(body)


def _key(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None
