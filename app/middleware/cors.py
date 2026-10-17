"""Allow the frontend dev server to call the API from a browser.

Tighten allow_origins before any real deployment.
"""

from __future__ import annotations

from starlette.middleware.cors import CORSMiddleware

from .requestid import HEADER_REQUEST_ID

ALLOW_HEADERS = ["Origin", "Content-Length", "Content-Type", "Authorization", HEADER_REQUEST_ID]
ALLOW_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]


def cors() -> tuple[type, dict]:
    """Return the middleware class and kwargs for app.add_middleware."""
    return (
        CORSMiddleware,
        {
            "allow_origins": ["*"],
            "allow_methods": ALLOW_METHODS,
            "allow_headers": ALLOW_HEADERS,
            "allow_credentials": False,
        },
    )
