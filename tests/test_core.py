from __future__ import annotations

import uuid
from contextlib import contextmanager

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from app.config import Config
from app.middleware.auth import get_user_id
from app.platform.ai.mock import Mock
from app.server import create_app


class _FakeConn:
    def execute(self, _sql: str) -> None:
        return None


class FakePool:
    def __init__(self, up: bool = True) -> None:
        self.up = up
        self.closed = False

    @contextmanager
    def connection(self, timeout: float | None = None):
        if not self.up:
            raise RuntimeError("database down")
        yield _FakeConn()

    def close(self) -> None:
        self.closed = True


def make_app(pool: FakePool | None = None):
    cfg = Config(app_env="test", jwt_secret="test-secret", jwt_ttl="1h")
    app = create_app(cfg, pool or FakePool(), Mock())

    @app.get("/secure")
    def secure(user_id: str = Depends(get_user_id)) -> dict:
        return {"data": {"user_id": user_id}}

    @app.get("/boom")
    def boom() -> dict:
        raise RuntimeError("kaboom")

    return app, cfg


@pytest.fixture
def client():
    app, cfg = make_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c, cfg


def test_live_is_ok(client):
    c, _ = client
    r = c.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"data": {"status": "ok"}}


def test_ready_ok_when_db_up(client):
    c, _ = client
    r = c.get("/readyz")
    assert r.status_code == 200
    assert r.json() == {"data": {"status": "ok"}}


def test_ready_503_when_db_down():
    app, _ = make_app(FakePool(up=False))
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/readyz")
    assert r.status_code == 503
    assert r.json() == {"error": {"code": "not_ready", "message": "database unavailable"}}


def test_request_id_echoed(client):
    c, _ = client
    r = c.get("/healthz", headers={"X-Request-ID": "abc-123"})
    assert r.headers["X-Request-ID"] == "abc-123"

    generated = c.get("/healthz").headers["X-Request-ID"]
    assert generated


def test_login_returns_deterministic_user_id(client):
    c, _ = client
    r = c.post("/api/v1/auth/login", json={"email": "User@Example.com", "password": "pw"})
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["user_id"] == str(uuid.uuid5(uuid.NAMESPACE_OID, "user@example.com"))
    assert body["token"]


def test_login_rejects_bad_input(client):
    c, _ = client
    r = c.post("/api/v1/auth/login", json={"email": "not-an-email", "password": "pw"})
    assert r.status_code == 400
    assert r.json() == {"error": {"code": "bad_request", "message": "invalid request"}}

    r = c.post("/api/v1/auth/login", json={"email": "user@example.com", "password": ""})
    assert r.status_code == 400


def test_protected_requires_token(client):
    c, _ = client
    assert c.get("/secure").json()["error"]["code"] == "missing_token"

    r = c.get("/secure", headers={"Authorization": "Bearer "})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "missing_token"

    r = c.get("/secure", headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_token"


def test_protected_accepts_issued_token(client):
    c, _ = client
    login = c.post("/api/v1/auth/login", json={"email": "user@example.com", "password": "pw"})
    token = login.json()["data"]["token"]
    user_id = login.json()["data"]["user_id"]

    r = c.get("/secure", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json() == {"data": {"user_id": user_id}}


def test_unhandled_error_is_500_envelope(client):
    c, _ = client
    r = c.get("/boom")
    assert r.status_code == 500
    assert r.json() == {"error": {"code": "internal", "message": "internal error"}}
