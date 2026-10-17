"""Emit one structured log line per request."""

from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from .requestid import request_id

log = logging.getLogger("app.http")


class LoggerMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        response = await call_next(request)

        level = logging.ERROR if response.status_code >= 500 else logging.INFO
        client = request.client
        log.log(
            level,
            "http request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "latency_ms": int((time.perf_counter() - start) * 1000),
                "request_id": request_id(request),
                "ip": client.host if client else "",
            },
        )
        return response
