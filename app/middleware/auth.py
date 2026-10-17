"""Reject requests without a valid bearer token.

The dependency returns the caller id and records it on request.state, the
FastAPI analog of Go's request-context identity.
"""

from __future__ import annotations

from fastapi import Request

from ..auth import ERR_INVALID_TOKEN, ERR_MISSING_TOKEN


def get_user_id(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    prefix = "Bearer "
    if not header.startswith(prefix) or not header[len(prefix):]:
        raise ERR_MISSING_TOKEN

    token = header[len(prefix):]
    try:
        user_id = request.app.state.tokens.parse(token)
    except Exception as exc:
        raise ERR_INVALID_TOKEN from exc

    request.state.user_id = user_id
    return user_id
