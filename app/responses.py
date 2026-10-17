"""The only place that writes HTTP responses.

Handlers return envelopes from ok/created and never build raw response bodies.
Every error is rendered here, so the envelope shape, status mapping, and error
logging live in one spot.
"""

from __future__ import annotations

import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import apperr

log = logging.getLogger("app.httpx")


def envelope(data: object = None, error: apperr.AppError | None = None) -> dict:
    """The uniform response body for every endpoint."""
    body: dict = {}
    if data is not None:
        body["data"] = data
    if error is not None:
        body["error"] = {"code": error.code, "message": error.message}
    return body


def ok(data: object) -> dict:
    """Envelope for a 200 response carrying data."""
    return envelope(data=data)


def created(data: object) -> dict:
    """Envelope for a 201 response carrying data."""
    return envelope(data=data)


def fail(request: Request, err: BaseException) -> JSONResponse:
    """Map err to an AppError, log the cause, and build the response."""
    error = apperr.from_error(err)

    if error.status >= HTTPStatus.INTERNAL_SERVER_ERROR:
        log.error(
            "request failed",
            extra={"code": error.code, "path": request.url.path, "err": str(error)},
            exc_info=error.cause,
        )

    response = JSONResponse(
        status_code=error.status,
        content=envelope(error=error),
    )
    return response


def code_for_status(status: int) -> str:
    """Machine code for a bare HTTP status, e.g. 404 -> "not_found"."""
    try:
        return HTTPStatus(status).name.lower()
    except ValueError:
        return "http_error"


def install_error_handlers(app: FastAPI) -> None:
    """Route every expected failure through fail() so responses stay uniform."""

    @app.exception_handler(apperr.AppError)
    async def _app_error(request: Request, exc: apperr.AppError) -> JSONResponse:
        return fail(request, exc)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return fail(request, apperr.wrap(apperr.ERR_BAD_REQUEST, exc))

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return fail(request, apperr.new(exc.status_code, code_for_status(exc.status_code), str(exc.detail)))
