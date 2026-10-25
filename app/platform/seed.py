"""Idempotent demo data seed."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import hash_password
from ..models import (
    Application,
    ApplicationEvent,
    ApplicationRevision,
    ApplicationStatus,
    Company,
    CompanyMembership,
    Evaluation,
    Offer,
    User,
)

log = logging.getLogger("app.seed")

_DEMO_PASSWORD = "password123"


def seed(session: Session) -> None:
    company = session.scalar(
        select(Company).where(Company.inn == "7701234567")
    )
    if company is None:
        company = Company(
            inn="7701234567",
            type="ООО",
            name="ООО Ромашка",
        )
        session.add(company)
        session.flush()

    client = _ensure_user(
        session,
        email="client@demo.ru",
        full_name="Клиент Демо",
    )

    membership = session.scalar(
        select(CompanyMembership).where(
            CompanyMembership.user_id == client.id,
            CompanyMembership.company_id == company.id,
        )
    )
    if membership is None:
        session.add(
            CompanyMembership(
                user_id=client.id,
                company_id=company.id,
                permissions=["*"],
                is_confirmed=True,
            )
        )

    _seed_demo_applications(session, company.id, client.id)
    session.commit()
    log.info("demo data seeded")


def _seed_demo_applications(
    session: Session,
    company_id: int,
    user_id: int,
) -> None:
    try:
        from .ai.ml_client import CreditEngineClient

        engine: Any | None = CreditEngineClient()
    except Exception as exc:
        log.warning(
            "credit engine unavailable, seeding DRAFT only",
            extra={"err": str(exc)},
        )
        engine = None

    if engine is None:
        _ensure_application(
            session,
            company_id=company_id,
            user_id=user_id,
            product_id=1,
            amount=500_000,
            term_months=12,
            company_age_months=24,
            status=ApplicationStatus.DRAFT,
            purpose="Пополнение оборотных средств",
        )
        return

    # Order matters: list is sorted by id DESC, so accepted is shown first.
    _ensure_application(
        session,
        company_id=company_id,
        user_id=user_id,
        product_id=2,
        amount=1_000_000,
        term_months=24,
        company_age_months=30,
        status=ApplicationStatus.REJECTED,
        purpose="Покупка оборудования",
        monthly_revenue=1_200_000,
        cash_available=-20_000,
        existing_debt=30_000,
        revenue_cv=0.6,
        customer_share=0.6,
        engine=engine,
    )
    _ensure_application(
        session,
        company_id=company_id,
        user_id=user_id,
        product_id=1,
        amount=1_000_000,
        term_months=24,
        company_age_months=36,
        status=ApplicationStatus.NEEDS_INFO,
        purpose="Пополнение оборотных средств",
        monthly_revenue=None,
        cash_available=None,
        existing_debt=None,
        revenue_cv=0.15,
        customer_share=0.25,
        engine=engine,
    )
    _ensure_application(
        session,
        company_id=company_id,
        user_id=user_id,
        product_id=2,
        amount=5_000_000,
        term_months=24,
        company_age_months=36,
        status=ApplicationStatus.OFFER_MADE,
        purpose="Покупка оборудования",
        monthly_revenue=1_200_000,
        cash_available=150_000,
        existing_debt=30_000,
        revenue_cv=0.15,
        customer_share=0.25,
        engine=engine,
    )
    _ensure_application(
        session,
        company_id=company_id,
        user_id=user_id,
        product_id=1,
        amount=1_000_000,
        term_months=24,
        company_age_months=36,
        status=ApplicationStatus.OFFER_ACCEPTED,
        purpose="Пополнение оборотных средств",
        monthly_revenue=1_500_000,
        cash_available=400_000,
        existing_debt=50_000,
        revenue_cv=0.15,
        customer_share=0.25,
        engine=engine,
    )


def _ensure_application(
    session: Session,
    *,
    company_id: int,
    user_id: int,
    product_id: int,
    amount: int,
    term_months: int,
    company_age_months: int,
    status: ApplicationStatus,
    purpose: str,
    monthly_revenue: float | None = None,
    cash_available: float | None = None,
    existing_debt: float | None = None,
    revenue_cv: float = 0.15,
    customer_share: float = 0.25,
    engine: Any | None = None,
) -> None:
    existing = session.scalars(
        select(Application).where(
            Application.company_id == company_id,
            Application.product_id == product_id,
            Application.status == status,
        )
    ).all()
    for application in existing:
        revision = (
            session.get(ApplicationRevision, application.current_revision_id)
            if application.current_revision_id is not None
            else None
        )
        if revision is not None and int(revision.data.get("amount", 0)) == amount:
            return

    if status != ApplicationStatus.DRAFT and engine is None:
        log.warning("credit engine unavailable, skipping demo application")
        return

    engine_result: dict[str, Any] | None = None
    if status != ApplicationStatus.DRAFT:
        try:
            engine_result = engine.evaluate_sync(
                {
                    "application_id": "seed",
                    "revision_id": 1,
                    "revision_version": 1,
                    "product_id": product_id,
                    "amount": amount,
                    "term_months": term_months,
                    "company_age_months": company_age_months,
                    "monthly_revenue": monthly_revenue,
                    "monthly_cash_available_for_debt_service_rub": cash_available,
                    "revenue_cv_12m": revenue_cv,
                    "largest_customer_share": customer_share,
                    "credit_report_consent_valid": True,
                    **(
                        {"existing_debt": existing_debt}
                        if existing_debt is not None
                        else {}
                    ),
                }
            )
        except Exception as exc:
            log.warning(
                "credit engine failed during seed, skipping demo application",
                extra={"err": str(exc)},
            )
            return

        if status in {
            ApplicationStatus.OFFER_MADE,
            ApplicationStatus.OFFER_ACCEPTED,
        } and (
            engine_result.get("decision") not in {"APPROVED", "COUNTEROFFER"}
            or engine_result.get("offer") is None
        ):
            log.warning(
                "credit engine did not produce an offer for demo seed",
                extra={
                    "decision": engine_result.get("decision"),
                    "reason_codes": engine_result.get("reason_codes"),
                },
            )
            return

    application = Application(
        company_id=company_id,
        product_id=product_id,
        status=status,
    )
    session.add(application)
    session.flush()

    revision_data = {
        "amount": amount,
        "term_months": term_months,
        "company_age_months": company_age_months,
        "monthly_revenue": monthly_revenue,
        "monthly_cash_available_for_debt_service_rub": cash_available,
        "revenue_cv_12m": revenue_cv,
        "largest_customer_share": customer_share,
        "credit_report_consent_valid": True,
        "purpose": purpose,
        "has_collateral": False,
        "existing_debt": existing_debt if existing_debt is not None else 0,
    }
    revision = ApplicationRevision(
        application_id=application.id,
        version=1,
        data=revision_data,
    )
    session.add(revision)
    session.flush()
    application.current_revision_id = revision.id

    transitions: list[tuple[ApplicationStatus | None, ApplicationStatus]] = [
        (None, ApplicationStatus.DRAFT),
    ]
    if status != ApplicationStatus.DRAFT:
        transitions.extend(
            [
                (ApplicationStatus.DRAFT, ApplicationStatus.SUBMITTED),
                (ApplicationStatus.SUBMITTED, ApplicationStatus.INTAKE_CHECK),
                (ApplicationStatus.INTAKE_CHECK, ApplicationStatus.ENRICHMENT),
                (ApplicationStatus.ENRICHMENT, ApplicationStatus.SCORING),
            ]
        )
        if status == ApplicationStatus.NEEDS_INFO:
            transitions.append(
                (ApplicationStatus.SCORING, ApplicationStatus.NEEDS_INFO)
            )
        elif status == ApplicationStatus.REJECTED:
            transitions.append(
                (ApplicationStatus.SCORING, ApplicationStatus.REJECTED)
            )
        elif status == ApplicationStatus.OFFER_MADE:
            transitions.append(
                (ApplicationStatus.SCORING, ApplicationStatus.OFFER_MADE)
            )
        elif status == ApplicationStatus.OFFER_ACCEPTED:
            transitions.extend(
                [
                    (ApplicationStatus.SCORING, ApplicationStatus.OFFER_MADE),
                    (
                        ApplicationStatus.OFFER_MADE,
                        ApplicationStatus.OFFER_ACCEPTED,
                    ),
                ]
            )

    for from_status, to_status in transitions:
        session.add(
            ApplicationEvent(
                application_id=application.id,
                event_type=(
                    "CREATED" if from_status is None else to_status.value
                ),
                from_status=from_status,
                to_status=to_status,
                actor_id=user_id,
                payload={"seed": True},
            )
        )
        if to_status == status:
            break

    if engine_result is not None:
        reasons = engine_result.get("reasons") or [
            {"code": code, "text": code}
            for code in engine_result.get("reason_codes", [])
        ]
        evaluation = Evaluation(
            application_id=application.id,
            revision_id=revision.id,
            decision=engine_result["decision"],
            risk_score=engine_result["risk_score"],
            risk_category=engine_result.get("risk_band"),
            offer_data=engine_result.get("offer") or {},
            reason_codes=reasons,
            risk_details=engine_result.get("risk_details"),
            missing_fields=list(engine_result.get("missing_fields", [])),
            next_action=engine_result.get("next_action"),
            engine_version=engine_result["engine_version"],
            policy_version=engine_result["policy_version"],
        )
        session.add(evaluation)
        session.flush()

        engine_offer = engine_result.get("offer")
        if engine_offer is not None:
            session.add(
                Offer(
                    application_id=application.id,
                    evaluation_id=evaluation.id,
                    amount=float(engine_offer["amount"]),
                    term=int(engine_offer["term"]),
                    rate=float(engine_offer["annual_rate"]),
                    payment=float(engine_offer["monthly_payment_rub"]),
                    expires_at=datetime.now(timezone.utc) + timedelta(days=7),
                    status=(
                        "accepted"
                        if status == ApplicationStatus.OFFER_ACCEPTED
                        else "offered"
                    ),
                )
            )
    session.flush()


def _ensure_user(
    session: Session,
    *,
    email: str,
    full_name: str,
) -> User:
    user = session.scalar(select(User).where(User.email == email))
    if user is not None:
        return user

    user = User(
        email=email,
        password_hash=hash_password(_DEMO_PASSWORD),
        full_name=full_name,
    )
    session.add(user)
    session.flush()
    return user
