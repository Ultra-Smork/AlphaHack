"""Evaluation-service boundary and local mock implementation."""

from __future__ import annotations

from typing import Any, Protocol

import httpx

from ...config import Config

_TIMEOUT_SECONDS = 10.0
_MAX_ERROR_BODY = 512
_OFFER_RATE = 20.0


class MLError(RuntimeError):
    """The evaluation service failed or returned an invalid response."""


class MLClient(Protocol):
    async def evaluate(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return decision, risk, offer, reason_codes, and versions."""
        ...


class MockMLClient:
    async def evaluate(self, payload: dict[str, Any]) -> dict[str, Any]:
        amount = int(payload["amount"])
        term_months = int(payload["term_months"])
        company_age_months = int(payload["company_age_months"])

        if amount > 3_000_000 or company_age_months < 12:
            return {
                "decision": "DECLINED",
                "risk": 0.85,
                "offer": None,
                "reason_codes": [
                    "AMOUNT_TOO_HIGH" if amount > 3_000_000 else "COMPANY_TOO_YOUNG"
                ],
                "engine_version": "mock-2.0",
                "policy_version": "policy-v2",
            }

        if amount <= 1_000_000 and company_age_months >= 24:
            payment = _annuity(amount, _OFFER_RATE, term_months)
            revenue = payload.get("monthly_revenue")
            dscr = round(float(revenue) / payment, 2) if revenue and payment else 1.5
            return {
                "decision": "APPROVED",
                "risk": 0.18,
                "offer": {
                    "amount": float(amount),
                    "term": term_months,
                    "annual_rate": _OFFER_RATE,
                    "monthly_payment_rub": payment,
                    "dscr": max(dscr, 0.0),
                },
                "reason_codes": ["WITHIN_POLICY"],
                "engine_version": "mock-2.0",
                "policy_version": "policy-v2",
            }

        return {
            "decision": "MANUAL_REVIEW",
            "risk": 0.52,
            "offer": None,
            "reason_codes": ["OUT_OF_AUTO_POLICY"],
            "engine_version": "mock-2.0",
            "policy_version": "policy-v2",
        }


class HTTPMLClient:
    def __init__(self, base_url: str) -> None:
        self._url = base_url.rstrip("/") + "/evaluate"

    async def evaluate(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                response = await client.post(self._url, json=payload)
        except httpx.HTTPError as exc:
            raise MLError(f"ml: request failed: {exc}") from exc

        if response.status_code != 200:
            body = response.text[:_MAX_ERROR_BODY]
            raise MLError(f"ml: status {response.status_code}: {body}")

        try:
            body = response.json()
        except ValueError as exc:
            raise MLError(f"ml: invalid json: {exc}") from exc
        if not isinstance(body, dict):
            raise MLError("ml: response must be a JSON object")
        return body


def get_ml_client(cfg: Config) -> MLClient:
    if cfg.ml_mode == "mock":
        return MockMLClient()
    if cfg.ml_mode == "http":
        return HTTPMLClient(cfg.ml_base_url)
    raise ValueError(f"ml: unknown ML_MODE {cfg.ml_mode!r}")


def _annuity(amount: float, annual_rate: float, term_months: int) -> float:
    monthly_rate = annual_rate / 100 / 12
    if monthly_rate == 0:
        return round(amount / term_months, 2)
    payment = amount * monthly_rate / (1 - (1 + monthly_rate) ** -term_months)
    return round(payment, 2)
