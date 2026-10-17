"""Turn an unhandled exception into a 500 envelope and log it.

Mirrors gin.Recovery: the process keeps serving, and no stack trace leaks to
the client.
"""

from __future__ import annotations

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from .. import apperr, responses

log = logging.getLogger("app.recovery")


class RecoveryMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        try:
            return await call_next(request)
        except apperr.AppError:
            raise
        except Exception as exc:
            return responses.fail(request, apperr.wrap(apperr.ERR_INTERNAL, exc))
