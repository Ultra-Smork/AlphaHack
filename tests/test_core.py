from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import Config
from app.platform import db
from app.platform.ai.ml_client import CreditEngineClient
from app.server import create_app


@pytest.fixture
def client():
    cfg = Config(
        app_env="test",
        database_url="sqlite:///:memory:",
        jwt_secret="test-secret-key-at-least-32-bytes",
        ml_mode="mock",
    )
    database = db.open_db(cfg)
    db.auto_migrate(database.engine, drop_on_start=True)
    app = create_app(cfg, database)
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
                "credit_report_consent_valid": True,
            },
        },
    )
    assert response.status_code == 200
    return response.json()["data"]


def test_health_endpoints(client):
    assert client.get("/health").json() == {"data": {"status": "ok"}}
    assert client.get("/healthz").json() == {"data": {"status": "ok"}}
    assert client.get("/readyz").json() == {"data": {"status": "ok"}}


def test_cors_allows_idempotency_key(client):
    response = client.options(
        "/api/applications",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,idempotency-key",
        },
    )
    assert response.status_code == 200
    allowed = response.headers["access-control-allow-headers"].lower()
    assert "idempotency-key" in allowed


def test_application_amount_limit(client):
    token = login(client, "client@demo.ru")
    response = client.post(
        "/api/applications",
        headers=auth(token),
        json={
            "product_id": 1,
            "data": {
                "amount": 1_000_000_001,
                "term_months": 12,
                "company_age_months": 24,
                "monthly_revenue": 100_000,
            },
        },
    )
    assert response.status_code == 400


def test_credit_engine_client_typical_request():
    result = asyncio.run(
        CreditEngineClient().evaluate(
            {
                "application_id": 1,
                "revision_id": 1,
                "revision_version": 1,
                "product_id": 1,
                "amount": 1_000_000,
                "term_months": 24,
                "company_age_months": 36,
                "monthly_revenue": 1_500_000,
                "monthly_cash_available_for_debt_service_rub": 400_000,
                "existing_debt": 50_000,
                "credit_report_consent_valid": True,
            }
        )
    )
    assert result["decision"] == "APPROVED"
    assert result["risk_score"] == 100
    assert result["risk_band"] == "LOW"
    assert result["offer"]["amount"] == 1_000_000
    assert result["offer"]["annual_rate"] == 0.24
    assert result["offer"]["monthly_payment_rub"] == 52_871.10
    assert result["offer"]["dscr"] == 3.888361
    assert result["reasons"][0]["code"] == "DEMO_POLICY_PASSED"
    assert result["reasons"][0]["text"]


def test_credit_engine_product_limit_explanation():
    result = asyncio.run(
        CreditEngineClient().evaluate(
            {
                "application_id": 2,
                "revision_id": 1,
                "revision_version": 1,
                "product_id": 2,
                "amount": 1_000_000,
                "term_months": 24,
                "company_age_months": 18,
                "monthly_revenue": 1_200_000,
                "monthly_cash_available_for_debt_service_rub": 150_000,
                "existing_debt": 30_000,
                "credit_report_consent_valid": True,
            }
        )
    )
    assert result["decision"] == "DECLINED"
    reason = result["reasons"][0]
    assert reason["code"] == "PRODUCT_BUSINESS_AGE_REQUIREMENT"
    assert reason["details"]["current"] == "18 мес."
    assert "24 мес." in reason["details"]["limit"]
    assert reason["details"]["action"]


def test_submit_runs_through_credit_engine():
    cfg = Config(
        app_env="test",
        database_url="sqlite:///:memory:",
        jwt_secret="test-secret-key-at-least-32-bytes",
        ml_mode="engine",
    )
    database = db.open_db(cfg)
    db.auto_migrate(database.engine)
    app = create_app(cfg, database)
    with TestClient(app) as test_client:
        token = login(test_client, "client@demo.ru")
        application = create_application(test_client, token)
        submitted = test_client.post(
            f"/api/applications/{application['id']}/submit",
            headers=auth(token),
        )
        assert submitted.status_code == 200
        detail = submitted.json()["data"]
        assert detail["status"] == "OFFER_MADE"
        assert detail["evaluations"][0]["risk_score"] == 100
        assert detail["evaluations"][0]["risk_category"] == "LOW"
        assert detail["evaluations"][0]["reason_codes"][0]["code"] == "DEMO_POLICY_PASSED"
        assert detail["offers"][0]["dscr"] is not None


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


def test_young_business_requires_info(client):
    token = login(client, "client@demo.ru")
    application = create_application(
        client,
        token,
        amount=1_000_000,
        term_months=18,
        company_age_months=6,
    )

    submitted = client.post(
        f"/api/applications/{application['id']}/submit",
        headers=auth(token),
    )
    assert submitted.status_code == 200
    assert submitted.json()["data"]["status"] == "NEEDS_INFO"


def test_bank_endpoints_removed(client):
    token = login(client, "client@demo.ru")
    assert client.get("/api/bank/applications", headers=auth(token)).status_code == 404

    bank_login = client.post(
        "/api/auth/login",
        json={"email": "bank@demo.ru", "password": "password123"},
    )
    assert bank_login.status_code == 401


def test_decline_offer(client):
    token = login(client, "client@demo.ru")
    application = create_application(client, token)
    application_id = application["id"]

    submitted = client.post(
        f"/api/applications/{application_id}/submit",
        headers=auth(token),
    ).json()["data"]
    offer_id = submitted["offer"]["id"]

    headers = {**auth(token), "Idempotency-Key": "decline-1"}
    declined = client.post(
        f"/api/applications/{application_id}/offers/{offer_id}/decline",
        headers=headers,
    )
    assert declined.status_code == 200
    assert declined.json()["data"]["status"] == "OFFER_DECLINED"
    assert declined.json()["data"]["offer"]["status"] == "declined"

    retry = client.post(
        f"/api/applications/{application_id}/offers/{offer_id}/decline",
        headers=headers,
    )
    assert retry.status_code == 200
    assert retry.json() == declined.json()

    sign = client.post(
        f"/api/applications/{application_id}/sign",
        headers=auth(token),
    )
    assert sign.status_code == 404


def test_needs_info_can_be_updated_and_resubmitted(client):
    token = login(client, "client@demo.ru")
    application = create_application(
        client,
        token,
        amount=1_000_000,
        term_months=18,
        company_age_months=6,
    )
    application_id = application["id"]

    first = client.post(
        f"/api/applications/{application_id}/submit",
        headers=auth(token),
    )
    assert first.json()["data"]["status"] == "NEEDS_INFO"

    updated = client.patch(
        f"/api/applications/{application_id}",
        headers=auth(token),
        json={
            "expected_revision": 1,
            "data": {
                "amount": 1_000_000,
                "term_months": 18,
                "company_age_months": 30,
                "monthly_revenue": 500_000,
            },
        },
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["status"] == "NEEDS_INFO"
    assert updated.json()["data"]["revision"]["version"] == 2

    second = client.post(
        f"/api/applications/{application_id}/submit",
        headers=auth(token),
    )
    assert second.status_code == 200
    assert second.json()["data"]["status"] == "OFFER_MADE"


def test_withdraw_after_accept_and_terminal_guard(client):
    token = login(client, "client@demo.ru")
    application = create_application(client, token)
    application_id = application["id"]

    offer = client.post(
        f"/api/applications/{application_id}/submit",
        headers=auth(token),
    ).json()["data"]["offer"]

    accepted = client.post(
        f"/api/applications/{application_id}/offers/{offer['id']}/accept",
        headers=auth(token),
    )
    assert accepted.json()["data"]["status"] == "OFFER_ACCEPTED"

    withdrawn = client.post(
        f"/api/applications/{application_id}/withdraw",
        headers=auth(token),
    )
    assert withdrawn.status_code == 200
    assert withdrawn.json()["data"]["status"] == "WITHDRAWN"

    again = client.post(
        f"/api/applications/{application_id}/withdraw",
        headers=auth(token),
    )
    assert again.status_code == 409
