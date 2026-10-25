"""Issue and verify access tokens. Has no dependency on the HTTP layer."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt

from ..apperr import new

# Token errors surfaced by the auth dependency.
ERR_MISSING_TOKEN = new(401, "missing_token", "authorization token required")
ERR_INVALID_TOKEN = new(401, "invalid_token", "invalid or expired token")


class TokenManager:
    """Sign and verify HS256 access tokens."""

    def __init__(self, secret: str, ttl: timedelta) -> None:
        self._secret = secret
        self._ttl = ttl

    def issue(self, user_id: str) -> str:
        """Return a signed token for the user."""
        now = datetime.now(timezone.utc)
        claims = {
            "sub": user_id,
            "uid": user_id,
            "iat": now,
            "exp": now + self._ttl,
        }
        try:
            return jwt.encode(claims, self._secret, algorithm="HS256")
        except jwt.PyJWTError as exc:
            raise RuntimeError(f"auth: sign: {exc}") from exc

    def parse(self, token: str) -> str:
        """Verify a token and return the user id, raising on any failure."""
        try:
            claims = jwt.decode(token, self._secret, algorithms=["HS256"])
        except jwt.PyJWTError as exc:
            raise ValueError(f"auth: invalid token: {exc}") from exc

        user_id = claims.get("uid") or claims.get("sub")
        if not user_id:
            raise ValueError("auth: token missing user id")
        return str(user_id)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, expected = stored.split("$", 1)
    except ValueError:
        return False
    digest = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return hmac.compare_digest(digest, expected)
