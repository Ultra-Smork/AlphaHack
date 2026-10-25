"""Client application endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session

from .. import responses
from ..models import User
from ..platform.db import get_db
from ..schemas import ApplicationCreate, ApplicationUpdate
from ..services import application_service as service
from .auth import get_current_user

router = APIRouter()


@router.get("/applications")
def list_applications(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    items = service.list_client_applications(db, user)
    return responses.ok([item.model_dump(mode="json") for item in items])


@router.post("/applications")
def create_application(
    payload: ApplicationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    result = service.create_application(db, user, payload)
    return responses.ok(result.model_dump(mode="json"))


@router.get("/applications/{application_id}")
def get_application(
    application_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    result = service.get_application(db, user, application_id)
    return responses.ok(result.model_dump(mode="json"))


@router.patch("/applications/{application_id}")
def update_application(
    application_id: int,
    payload: ApplicationUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    result = service.update_application(db, user, application_id, payload)
    return responses.ok(result.model_dump(mode="json"))


@router.post("/applications/{application_id}/submit")
async def submit_application(
    application_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    key = _key(idempotency_key)
    request_hash = _hash(request, {}) if key else ""
    if key:
        cached = service.get_idempotent_response(db, key, request_hash)
        if cached is not None:
            return responses.ok(cached)

    result = await service.submit_application(
        db, user, application_id, request.app.state.ml_client
    )
    body = result.model_dump(mode="json")
    if key:
        service.save_idempotent_response(db, key, request_hash, body)
    return responses.ok(body)


@router.post("/applications/{application_id}/offers/{offer_id}/accept")
def accept_offer(
    application_id: int,
    offer_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    key = _key(idempotency_key)
    request_hash = _hash(request, {}) if key else ""
    if key:
        cached = service.get_idempotent_response(db, key, request_hash)
        if cached is not None:
            return responses.ok(cached)

    result = service.accept_offer(db, user, application_id, offer_id)
    body = result.model_dump(mode="json")
    if key:
        service.save_idempotent_response(db, key, request_hash, body)
    return responses.ok(body)


@router.post("/applications/{application_id}/offers/{offer_id}/decline")
def decline_offer(
    application_id: int,
    offer_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    key = _key(idempotency_key)
    request_hash = _hash(request, {}) if key else ""
    if key:
        cached = service.get_idempotent_response(db, key, request_hash)
        if cached is not None:
            return responses.ok(cached)

    result = service.decline_offer(db, user, application_id, offer_id)
    body = result.model_dump(mode="json")
    if key:
        service.save_idempotent_response(db, key, request_hash, body)
    return responses.ok(body)


@router.post("/applications/{application_id}/withdraw")
def withdraw_application(
    application_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    result = service.withdraw_application(db, user, application_id)
    return responses.ok(result.model_dump(mode="json"))


def _key(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _hash(request: Request, payload: Any) -> str:
    return service.make_request_hash(request.method, request.url.path, payload)
