"""Assign a request id to each request, reusing an inbound one if present."""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

# HeaderRequestID is echoed on every response.
HEADER_REQUEST_ID = "X-Request-ID"


def request_id(request: Request) -> str:
    """Return the current request id."""
    return getattr(request.state, "request_id", "")


class RequestIDMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        rid = request.headers.get(HEADER_REQUEST_ID) or str(uuid.uuid4())
        request.state.request_id = rid
        response = await call_next(request)
        response.headers[HEADER_REQUEST_ID] = rid
        return response
