"""Health handlers. Handlers translate requests into service calls and
responses via responses; they hold no business logic.
"""

from __future__ import annotations

from fastapi import APIRouter
from psycopg_pool import ConnectionPool

from .. import apperr, responses
from ..platform import db

_PING_TIMEOUT_SECONDS = 2.0


def new_health_router(pool: ConnectionPool) -> APIRouter:
    router = APIRouter()

    @router.get("/healthz")
    def live() -> dict:
        """Liveness: the process is running."""
        return responses.ok({"status": "ok"})

    @router.get("/readyz")
    def ready() -> dict:
        """Readiness: the process can serve traffic (database reachable)."""
        try:
            db.ping(pool, _PING_TIMEOUT_SECONDS)
        except Exception as exc:
            raise _not_ready(exc) from exc
        return responses.ok({"status": "ok"})

    return router


def _not_ready(cause: BaseException) -> apperr.AppError:
    return apperr.wrap(
        apperr.new(503, "not_ready", "database unavailable"),
        cause,
    )
