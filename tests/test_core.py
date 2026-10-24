from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import Config
from app.platform import db
from app.platform.ai.mock import Mock
from app.server import create_app


@pytest.fixture
def client():
    cfg = Config(
        app_env="test",
        database_url="sqlite:///:memory:",
        jwt_secret="test-secret-key-at-least-32-bytes",
    )
    database = db.open_db(cfg)
    db.auto_migrate(database.engine, drop_on_start=True)
    app = create_app(cfg, database, Mock())
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def login(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_application(
    client: TestClient,
    token: str,
    *,
    amount: int = 900_000,
    term_months: int = 12,
    company_age_months: int = 30,
) -> dict:
    response = client.post(
        "/api/applications",
        headers=auth(token),
        json={
            "product_id": 1,
            "data": {
                "amount": amount,
                "term_months": term_months,
                "company_age_months": company_age_months,
                "monthly_revenue": 500_000,
            },
        },
    )
    assert response.status_code == 200
    return response.json()["data"]


def test_health_endpoints(client):
    assert client.get("/health").json() == {"data": {"status": "ok"}}
    assert client.get("/healthz").json() == {"data": {"status": "ok"}}
    assert client.get("/readyz").json() == {"data": {"status": "ok"}}


def test_legacy_schema_fails_fast(tmp_path):
    cfg = Config(
        app_env="test",
        database_url=f"sqlite:///{tmp_path / 'legacy.db'}",
        jwt_secret="test-secret-key-at-least-32-bytes",
    )
    database = db.open_db(cfg)
    try:
        with database.engine.begin() as conn:
            conn.execute(
                text("CREATE TABLE users (id INTEGER PRIMARY KEY, phone TEXT)")
            )
        with pytest.raises(RuntimeError, match="incompatible schema"):
            db.auto_migrate(database.engine)
    finally:
        database.close()


def test_login_and_invalid_credentials(client):
    token = login(client, "client@demo.ru")
    assert token

    response = client.post(
        "/api/auth/login",
        json={"email": "client@demo.ru", "password": "wrong"},
    )
    assert response.status_code == 401
    assert response.json() == {
        "error": {"code": "invalid_credentials", "message": "invalid email or password"}
    }


def test_protected_endpoint_requires_token(client):
    response = client.get("/api/applications")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "missing_token"


def test_happy_path_to_offer_made_with_idempotent_submit(client):
    token = login(client, "client@demo.ru")
    application = create_application(client, token)
    application_id = application["id"]
    assert application["status"] == "DRAFT"
    assert application["revision"]["version"] == 1

    headers = {
        **auth(token),
        "Idempotency-Key": "submit-happy-1",
    }
    response = client.post(
        f"/api/applications/{application_id}/submit",
        headers=headers,
    )
    assert response.status_code == 200
    submitted = response.json()["data"]
    assert submitted["status"] == "OFFER_MADE"
    assert submitted["offer"]["amount"] == 900_000
    assert submitted["offer"]["term"] == 12

    retry = client.post(
        f"/api/applications/{application_id}/submit",
        headers=headers,
    )
    assert retry.status_code == 200
    assert retry.json() == response.json()

    detail = client.get(
        f"/api/applications/{application_id}",
        headers=auth(token),
    ).json()["data"]
    assert detail["status"] == "OFFER_MADE"
    assert [event["to_status"] for event in detail["events"]][-1] == "OFFER_MADE"


def test_patch_revision_conflict(client):
    token = login(client, "client@demo.ru")
    application = create_application(client, token)
    application_id = application["id"]

    updated = client.patch(
        f"/api/applications/{application_id}",
        headers=auth(token),
        json={
            "expected_revision": 1,
            "data": {
                "amount": 950_000,
                "term_months": 18,
                "company_age_months": 30,
                "monthly_revenue": 500_000,
            },
        },
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["revision"]["version"] == 2

    stale = client.patch(
        f"/api/applications/{application_id}",
        headers=auth(token),
        json={
            "expected_revision": 1,
            "data": {
                "amount": 950_000,
                "term_months": 18,
                "company_age_months": 30,
                "monthly_revenue": 500_000,
            },
        },
    )
    assert stale.status_code == 409


def test_manual_review_and_bank_queue(client):
    client_token = login(client, "client@demo.ru")
    bank_token = login(client, "bank@demo.ru")
    application = create_application(
        client,
        client_token,
        amount=1_500_000,
        term_months=18,
        company_age_months=30,
    )

    submitted = client.post(
        f"/api/applications/{application['id']}/submit",
        headers=auth(client_token),
    )
    assert submitted.status_code == 200
    assert submitted.json()["data"]["status"] == "MANUAL_REVIEW"

    forbidden = client.get("/api/bank/applications", headers=auth(client_token))
    assert forbidden.status_code == 403

    queue = client.get("/api/bank/applications", headers=auth(bank_token))
    assert queue.status_code == 200
    assert [item["id"] for item in queue.json()["data"]] == [application["id"]]

    reviewed = client.post(
        f"/api/bank/applications/{application['id']}/review",
        headers=auth(bank_token),
        json={"decision": "APPROVE", "reason": "ok"},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["data"]["status"] == "OFFER_MADE"
    assert reviewed.json()["data"]["offer"]["rate"] == 20.0


def test_sign_requires_idempotency_key(client):
    token = login(client, "client@demo.ru")
    application = create_application(client, token)
    application_id = application["id"]

    submitted = client.post(
        f"/api/applications/{application_id}/submit",
        headers=auth(token),
    ).json()["data"]
    offer_id = submitted["offer"]["id"]

    accepted = client.post(
        f"/api/applications/{application_id}/offers/{offer_id}/accept",
        headers=auth(token),
    )
    assert accepted.status_code == 200
    assert accepted.json()["data"]["status"] == "OFFER_ACCEPTED"

    missing = client.post(
        f"/api/applications/{application_id}/sign",
        headers=auth(token),
    )
    assert missing.status_code == 400

    signed = client.post(
        f"/api/applications/{application_id}/sign",
        headers={**auth(token), "Idempotency-Key": "sign-1"},
    )
    assert signed.status_code == 200
    assert signed.json()["data"]["status"] == "DISBURSED"
    assert signed.json()["data"]["contract"]["status"] == "signed"
    assert signed.json()["data"]["disbursement"]["status"] == "success"
