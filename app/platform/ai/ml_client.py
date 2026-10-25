"""Evaluation-service boundary and local credit-engine adapter."""

from __future__ import annotations

import logging
from typing import Any, Protocol

import httpx

from ...config import Config
from .credit_engine import POLICY, REASON_TEXT_RU, RequestError, evaluate

_TIMEOUT_SECONDS = 10.0
_MAX_ERROR_BODY = 512
_OFFER_RATE = 20.0

log = logging.getLogger("app.ml")

_PRODUCT_MAP = {
    1: "working_capital",
    2: "equipment",
}


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

        if amount > 500_000_000 or company_age_months < 3:
            return {
                "decision": "DECLINED",
                "risk_score": 85,
                "risk_band": "HIGH",
                "offer": None,
                "reason_codes": ["COMPANY_TOO_YOUNG"],
                "engine_version": "mock-2.0",
                "policy_version": "policy-v2",
            }

        if company_age_months >= 12:
            payment = _annuity(amount, _OFFER_RATE, term_months)
            revenue = payload.get("monthly_revenue")
            dscr = round(float(revenue) / payment, 2) if revenue and payment else 1.5
            return {
                "decision": "APPROVED",
                "risk_score": 18,
                "risk_band": "LOW",
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
            "decision": "NEED_INFO",
            "risk_score": 52,
            "risk_band": "MEDIUM",
            "offer": None,
            "reason_codes": ["ADDITIONAL_DATA_REQUIRED"],
            "engine_version": "mock-2.0",
            "policy_version": "policy-v2",
        }


class CreditEngineClient:
    async def evaluate(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.evaluate_sync(payload)

    def evaluate_sync(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = self._build_engine_request(payload)

        try:
            result = evaluate(request, staff_review=False)
        except RequestError as exc:
            raise MLError(
                "credit engine rejected request: " + "; ".join(exc.errors)
            ) from exc
        except Exception as exc:
            raise MLError(f"credit engine failed: {exc}") from exc

        decision = result["decision"]
        reason_codes = list(result.get("reason_codes", []))

        if decision == "MANUAL_REVIEW":
            log.error(
                "unexpected MANUAL_REVIEW from engine with staff_review=False",
                extra={
                    "application_id": request["application_id"],
                    "revision": request["revision"],
                    "reason_codes": reason_codes,
                },
            )
            decision = "REJECTED"
            reason_codes = ["MANUAL_REVIEW_FALLBACK", *reason_codes]

        risk = result.get("risk") or {}
        engine_offer = result.get("offer")
        offer = None
        if engine_offer:
            offer = {
                "amount": float(engine_offer["amount_rub"]),
                "term": int(engine_offer["term_months"]),
                "annual_rate": float(engine_offer["annual_rate"]),
                "monthly_payment_rub": float(engine_offer["monthly_payment_rub"]),
                "dscr": float(engine_offer["dscr"]),
                "repayment_type": engine_offer.get("repayment_type", "ANNUITY"),
                "fees_rub": engine_offer.get("fees_rub", 0),
                "insurance_rub": engine_offer.get("insurance_rub", 0),
                "collateral_required": engine_offer.get("collateral_required", False),
            }

        return {
            "decision": decision,
            "risk": float(risk.get("score", 0)) / 100,
            "risk_score": int(risk.get("score", 0)),
            "risk_band": risk.get("band"),
            "risk_details": {
                "factors": risk.get("factors", []),
                "calibrated_pd": risk.get("calibrated_pd"),
                "next_action": result.get("next_action"),
            },
            "offer": offer,
            "reason_codes": reason_codes,
            "reasons": _build_reasons(reason_codes, request, result),
            "missing_fields": list(result.get("missing_fields", [])),
            "next_action": result.get("next_action"),
            "engine_version": result.get("engine_version"),
            "policy_version": result.get("policy_version"),
            "schema_version": result.get("schema_version"),
            "demo": result.get("demo"),
        }

    @staticmethod
    def _build_engine_request(payload: dict[str, Any]) -> dict[str, Any]:
        raw_product = payload.get("product_id")
        if isinstance(raw_product, int):
            product_id = _PRODUCT_MAP.get(raw_product)
        else:
            product_id = raw_product if raw_product in _PRODUCT_MAP.values() else None
        if product_id is None:
            raise MLError(f"credit engine: unsupported product {raw_product!r}")

        revenue = payload.get("monthly_revenue")
        cash_available = payload.get("monthly_cash_available_for_debt_service_rub")
        if cash_available is None and isinstance(revenue, (int, float)) and revenue > 0:
            cash_available = float(revenue) * 0.3

        revenue_cv = payload.get("revenue_cv_12m")
        if revenue_cv is None:
            revenue_cv = 0.15
        customer_share = payload.get("largest_customer_share")
        if customer_share is None:
            customer_share = 0.25

        financials: dict[str, Any] = {
            "revenue_cv_12m": revenue_cv,
            "largest_customer_share": customer_share,
        }
        if payload.get("existing_debt") is not None:
            financials["existing_monthly_debt_service_rub"] = payload["existing_debt"]
        if isinstance(revenue, (int, float)) and revenue > 0:
            financials["monthly_revenue_rub"] = float(revenue)
        if cash_available is not None:
            financials["monthly_cash_available_for_debt_service_rub"] = float(
                cash_available
            )

        # TODO: заменить на реальные адаптеры (ЕГРЮЛ, БКИ, антифрод) в проде.
        checks = payload.get("checks") or {
            "registry": "active",
            "authority": "verified",
            "credit_history": "available",
            "fraud": "clear",
            "max_overdue_days_12m": 0,
        }

        revision = payload.get("revision_version")
        if revision is None:
            revision = payload.get("revision", payload.get("revision_id", 1))

        return {
            "application_id": str(payload["application_id"]),
            "revision": int(revision),
            "product_id": product_id,
            "requested_amount_rub": int(payload["amount"]),
            "requested_term_months": int(payload["term_months"]),
            "company": {"age_months": int(payload["company_age_months"])},
            "financials": financials,
            "checks": checks,
            "credit_report_consent_valid": bool(
                payload.get("credit_report_consent_valid", False)
            ),
        }


def _money(value: Any) -> str:
    if value is None:
        return '—'
    return f"{int(round(float(value))):,}".replace(",", " ") + " ₽"


def _build_reasons(
    reason_codes: list[str],
    request: dict[str, Any],
    result: dict[str, Any],
) -> list[dict[str, Any]]:
    reasons: list[dict[str, Any]] = []
    for code in reason_codes:
        reason: dict[str, Any] = {
            "code": code,
            "text": REASON_TEXT_RU.get(code, code),
        }
        details = _reason_details(code, request, result)
        if details:
            reason["details"] = details
        reasons.append(reason)
    return reasons


def _reason_details(
    code: str,
    request: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, str] | None:
    product = POLICY["products"].get(request["product_id"])
    if product is None:
        return None
    product_title = product["title"]
    offer = result.get("offer") or {}
    financials = request.get("financials") or {}
    cash = financials.get("monthly_cash_available_for_debt_service_rub")
    existing = financials.get("existing_monthly_debt_service_rub")

    if code == "PRODUCT_BUSINESS_AGE_REQUIREMENT":
        return {
            "title": "Возраст бизнеса",
            "current": f"{request['company']['age_months']} мес.",
            "limit": f"Минимум для «{product_title}»: {product['min_age_months']} мес.",
            "action": "Выберите другой продукт или подайте заявку позже.",
        }

    if code == "TERM_CHANGED_TO_PRODUCT_RANGE":
        return {
            "title": "Срок",
            "current": f"{request['requested_term_months']} мес.",
            "limit": (
                f"Для «{product_title}» доступно "
                f"{product['min_term_months']}–{product['max_term_months']} мес."
            ),
            "action": (
                f"Мы изменили срок на {offer.get('term_months')} мес. "
                "Проверьте предложение."
            ),
        }

    if code == "AMOUNT_LIMITED_BY_PRODUCT_OR_AFFORDABILITY":
        return {
            "title": "Сумма",
            "current": _money(request["requested_amount_rub"]),
            "limit": (
                f"По продукту: до {_money(product['max_amount_rub'])}; "
                f"по платёжеспособности: до {_money(offer.get('amount_rub'))}"
            ),
            "action": (
                "Уменьшите сумму или увеличьте доступный денежный поток."
            ),
        }

    if code == "NO_AFFORDABLE_OFFER":
        return {
            "title": "Платёжеспособность",
            "current": f"Доступно на платёж: {_money(cash)} в месяц",
            "limit": f"Нужен DSCR не ниже {float(POLICY['dscr_min']):g}",
            "action": (
                "Уменьшите сумму, увеличьте срок или снизьте текущую "
                "долговую нагрузку."
            ),
        }

    if code == "HIGH_DEMO_RISK":
        risk = result.get("risk") or {}
        return {
            "title": "Оценка риска",
            "current": f"{risk.get('score', 0)} из 100",
            "limit": "Для автоматического решения нужен низкий или средний риск.",
            "action": (
                "Улучшите денежный поток, снизьте концентрацию на одном клиенте "
                "и уменьшите долговую нагрузку."
            ),
        }

    if code == "INSUFFICIENT_CASH_FLOW":
        return {
            "title": "Денежный поток",
            "current": f"{_money(cash)} в месяц",
            "limit": "Должен быть больше нуля.",
            "action": "Увеличьте доступный денежный поток или уменьшите расходы.",
        }

    if code == "SEVERE_DELINQUENCY":
        return {
            "title": "Просрочки",
            "current": f"{request['checks']['max_overdue_days_12m']} дней",
            "limit": f"Допустимо меньше {POLICY['severe_overdue_days']} дней.",
            "action": "Погасите просроченную задолженность и подайте заявку позже.",
        }

    if code == "STRICTER_AFFORDABILITY":
        return {
            "title": "Проверка платёжеспособности",
            "current": "Применены повышенные требования",
            "limit": f"DSCR не ниже {float(POLICY['dscr_min_strict']):g}",
            "action": "Уменьшите сумму или увеличьте срок.",
        }

    if code == "NO_CREDIT_HISTORY":
        return {
            "title": "Кредитная история",
            "current": "История отсутствует",
            "limit": "Применена более строгая проверка платёжеспособности.",
            "action": "Уменьшите сумму или увеличьте срок.",
        }

    if code == "BUSINESS_INACTIVE":
        return {
            "title": "Статус бизнеса",
            "current": "Неактивен",
            "limit": "Для кредита нужен действующий бизнес.",
            "action": "Обновите статус бизнеса и подайте заявку снова.",
        }

    return None


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
    if cfg.ml_mode == "engine":
        return CreditEngineClient()
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
