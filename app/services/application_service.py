"""Credit application FSM, access checks, and idempotency helpers."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import apperr
from ..models import (
    Application,
    ApplicationEvent,
    ApplicationRevision,
    ApplicationStatus,
    CheckResult,
    CompanyMembership,
    Evaluation,
    IdempotencyKey,
    Offer,
    User,
)
from ..platform.ai.ml_client import MLClient, MLValidationError
from ..schemas import (
    AcceptOfferResponse,
    ApplicationCreate,
    ApplicationDetail,
    ApplicationSummary,
    ApplicationUpdate,
    DeclineOfferResponse,
    EvaluationOut,
    EventOut,
    MLEvaluation,
    MLRequest,
    OfferOut,
    QuestionnaireData,
    RevisionOut,
    WithdrawResponse,
)
from .notification_service import send_status_change_email

log = logging.getLogger("app.applications")

OFFER_TTL_DAYS = 7

_ALLOWED_TRANSITIONS: dict[ApplicationStatus, set[ApplicationStatus]] = {
    ApplicationStatus.DRAFT: {ApplicationStatus.SUBMITTED, ApplicationStatus.WITHDRAWN},
    ApplicationStatus.SUBMITTED: {ApplicationStatus.INTAKE_CHECK, ApplicationStatus.WITHDRAWN},
    ApplicationStatus.INTAKE_CHECK: {
        ApplicationStatus.ENRICHMENT,
        ApplicationStatus.NEEDS_INFO,
        ApplicationStatus.REJECTED,
        ApplicationStatus.WITHDRAWN,
    },
    ApplicationStatus.NEEDS_INFO: {
        ApplicationStatus.SUBMITTED,
        ApplicationStatus.WITHDRAWN,
    },
    ApplicationStatus.ENRICHMENT: {
        ApplicationStatus.SCORING,
        ApplicationStatus.NEEDS_INFO,
        ApplicationStatus.REJECTED,
        ApplicationStatus.WITHDRAWN,
    },
    ApplicationStatus.SCORING: {
        ApplicationStatus.OFFER_MADE,
        ApplicationStatus.NEEDS_INFO,
        ApplicationStatus.REJECTED,
        ApplicationStatus.WITHDRAWN,
    },
    ApplicationStatus.OFFER_MADE: {
        ApplicationStatus.OFFER_ACCEPTED,
        ApplicationStatus.OFFER_DECLINED,
        ApplicationStatus.OFFER_EXPIRED,
        ApplicationStatus.WITHDRAWN,
    },
    ApplicationStatus.OFFER_ACCEPTED: {ApplicationStatus.WITHDRAWN},
}


def list_client_applications(session: Session, user: User) -> list[ApplicationSummary]:
    company_id = _client_company_id(session, user)

    applications = session.scalars(
        select(Application)
        .where(Application.company_id == company_id)
        .order_by(Application.id.desc())
    ).all()

    result: list[ApplicationSummary] = []
    for application in applications:
        revision = _revision(session, application)
        data = _revision_data(revision)
        result.append(
            ApplicationSummary(
                id=application.id,
                company_id=application.company_id,
                product_id=application.product_id,
                status=application.status,
                current_revision_id=application.current_revision_id,
                current_revision=(
                    RevisionOut.model_validate(revision) if revision else None
                ),
                amount=data.get("amount"),
                term_months=data.get("term_months"),
                created_at=application.created_at,
            )
        )
    return result


def create_application(
    session: Session,
    user: User,
    payload: ApplicationCreate,
) -> ApplicationDetail:
    company_id = _client_company_id(session, user)

    application = Application(
        company_id=company_id,
        product_id=payload.product_id,
        status=ApplicationStatus.DRAFT,
    )
    session.add(application)
    session.flush()

    revision = ApplicationRevision(
        application_id=application.id,
        version=1,
        data=payload.data.model_dump(mode="json"),
    )
    session.add(revision)
    session.flush()

    application.current_revision_id = revision.id
    session.add(
        ApplicationEvent(
            application_id=application.id,
            event_type="CREATED",
            from_status=None,
            to_status=ApplicationStatus.DRAFT,
            actor_id=user.id,
            payload={"revision_id": revision.id, "version": revision.version},
        )
    )
    session.commit()
    return _application_detail(session, application)


def get_application(session: Session, user: User, application_id: int) -> ApplicationDetail:
    application = _client_application(session, user, application_id)
    return _application_detail(session, application)


def update_application(
    session: Session,
    user: User,
    application_id: int,
    payload: ApplicationUpdate,
) -> ApplicationDetail:
    application = _client_application(session, user, application_id)
    if application.status not in {
        ApplicationStatus.DRAFT,
        ApplicationStatus.NEEDS_INFO,
    }:
        raise _conflict("only DRAFT or NEEDS_INFO applications can be edited")

    current = _revision(session, application)
    if current is None:
        raise _conflict("application has no current revision")
    if current.version != payload.expected_revision:
        raise _conflict("revision conflict")

    revision = ApplicationRevision(
        application_id=application.id,
        version=current.version + 1,
        data=payload.data.model_dump(mode="json"),
    )
    session.add(revision)
    session.flush()

    application.current_revision_id = revision.id
    session.add(
        ApplicationEvent(
            application_id=application.id,
            event_type="REVISION_CREATED",
            from_status=application.status,
            to_status=application.status,
            actor_id=user.id,
            payload={"revision_id": revision.id, "version": revision.version},
        )
    )
    session.commit()
    return _application_detail(session, application)


async def submit_application(
    session: Session,
    user: User,
    application_id: int,
    ml_client: MLClient,
) -> ApplicationDetail:
    application = _client_application(session, user, application_id)
    if application.status not in {
        ApplicationStatus.DRAFT,
        ApplicationStatus.NEEDS_INFO,
    }:
        raise _conflict("only DRAFT or NEEDS_INFO applications can be submitted")

    revision = _revision(session, application)
    if revision is None:
        raise _conflict("application has no current revision")
    data = QuestionnaireData.model_validate(revision.data)

    ml_payload = MLRequest(
        application_id=application.id,
        revision_id=revision.id,
        revision_version=revision.version,
        product_id=application.product_id,
        amount=data.amount,
        term_months=data.term_months,
        company_age_months=data.company_age_months,
        monthly_revenue=data.monthly_revenue,
        monthly_cash_available_for_debt_service_rub=(
            data.monthly_cash_available_for_debt_service_rub
        ),
        revenue_cv_12m=data.revenue_cv_12m,
        largest_customer_share=data.largest_customer_share,
        credit_report_consent_valid=data.credit_report_consent_valid,
        purpose=data.purpose,
        has_collateral=data.has_collateral,
        existing_debt=data.existing_debt,
    )

    try:
        raw = await ml_client.evaluate(ml_payload.model_dump(mode="json"))
    except MLValidationError as exc:
        log.warning(
            "credit engine rejected application data",
            extra={"application_id": application.id, "errors": exc.errors},
        )
        details = "; ".join(exc.errors)
        raise apperr.new(
            422,
            "invalid_application_data",
            f"Проверьте данные заявки: {details}",
        ) from exc
    except Exception as exc:
        log.error(
            "ml evaluation failed",
            extra={"application_id": application.id, "err": str(exc)},
        )
        raise apperr.wrap(
            apperr.new(
                503,
                "engine_unavailable",
                "Сервис оценки временно недоступен. Попробуйте позже.",
            ),
            exc,
        ) from exc

    if not isinstance(raw, dict):
        log.error(
            "ml returned non-object response",
            extra={"application_id": application.id, "response_type": type(raw).__name__},
        )
        raise apperr.new(
            503,
            "invalid_engine_response",
            "Сервис оценки вернул некорректный ответ. Попробуйте позже.",
        )

    if raw.get("decision") == "MANUAL_REVIEW":
        log.error(
            "ml returned unsupported decision",
            extra={
                "application_id": application.id,
                "revision_id": revision.id,
                "decision": raw.get("decision"),
                "reason_codes": raw.get("reason_codes"),
                "engine_version": raw.get("engine_version"),
            },
        )
        raise apperr.new(
            503,
            "unsupported_ml_decision",
            "Сервис оценки вернул неподдерживаемое решение. Попробуйте позже.",
        )

    try:
        evaluation_result = MLEvaluation.model_validate(raw)
    except Exception as exc:
        log.error(
            "invalid ml response",
            extra={
                "application_id": application.id,
                "err": str(exc),
                "decision": raw.get("decision"),
            },
        )
        raise apperr.wrap(
            apperr.new(
                503,
                "invalid_engine_response",
                "Сервис оценки вернул некорректный ответ. Попробуйте позже.",
            ),
            exc,
        ) from exc

    _transition(session, application, ApplicationStatus.SUBMITTED, actor_id=user.id)
    _transition(session, application, ApplicationStatus.INTAKE_CHECK)

    completeness = "passed" if data.monthly_revenue is not None else "needs_info"
    _add_check(
        session,
        application.id,
        check_type="DATA_COMPLETENESS",
        status=completeness,
        source="mock",
        fixture_id="fixture:data:v1",
    )

    stop_factor = data.company_age_months < 6 or data.amount > 10_000_000
    _add_check(
        session,
        application.id,
        check_type="STOP_FACTOR",
        status="failed" if stop_factor else "passed",
        source="mock",
        fixture_id="fixture:stop-factor:v1",
    )

    _transition(session, application, ApplicationStatus.ENRICHMENT)
    _add_check(
        session,
        application.id,
        check_type="ENRICHMENT",
        status="passed",
        source="mock",
        fixture_id="fixture:enrichment:v1",
    )
    _transition(session, application, ApplicationStatus.SCORING)

    reasons = (
        [reason.model_dump(mode="json") for reason in evaluation_result.reasons]
        if evaluation_result.reasons
        else [
            {"code": code, "text": code}
            for code in evaluation_result.reason_codes
        ]
    )
    evaluation = Evaluation(
        application_id=application.id,
        revision_id=revision.id,
        decision=evaluation_result.decision,
        risk_score=evaluation_result.risk_score,
        risk_category=(
            evaluation_result.risk_band
            or (
                _risk_category(evaluation_result.risk_score)
                if evaluation_result.risk_score > 0
                else None
            )
        ),
        offer_data=(
            evaluation_result.offer.model_dump(mode="json")
            if evaluation_result.offer
            else {}
        ),
        reason_codes=reasons,
        risk_details=evaluation_result.risk_details or None,
        missing_fields=list(evaluation_result.missing_fields),
        next_action=evaluation_result.next_action,
        engine_version=evaluation_result.engine_version,
        policy_version=evaluation_result.policy_version,
    )
    session.add(evaluation)
    session.flush()

    if evaluation_result.decision in {"APPROVED", "COUNTEROFFER"}:
        if evaluation_result.offer is None:
            raise apperr.new(502, "ml_error", "approved decision without offer")
        offer = Offer(
            application_id=application.id,
            evaluation_id=evaluation.id,
            amount=evaluation_result.offer.amount,
            term=evaluation_result.offer.term,
            rate=evaluation_result.offer.annual_rate,
            payment=evaluation_result.offer.monthly_payment_rub,
            expires_at=_now() + timedelta(days=OFFER_TTL_DAYS),
            status="offered",
        )
        session.add(offer)
        session.flush()
        _transition(
            session,
            application,
            ApplicationStatus.OFFER_MADE,
            payload={"evaluation_id": evaluation.id, "offer_id": offer.id},
        )
        return _application_detail(session, application)

    if evaluation_result.decision == "NEED_INFO":
        _transition(
            session,
            application,
            ApplicationStatus.NEEDS_INFO,
            payload={"evaluation_id": evaluation.id},
        )
    else:
        _transition(
            session,
            application,
            ApplicationStatus.REJECTED,
            payload={"evaluation_id": evaluation.id},
        )

    return _application_detail(session, application)


def accept_offer(
    session: Session,
    user: User,
    application_id: int,
    offer_id: int,
) -> AcceptOfferResponse:
    application = _client_application(session, user, application_id)
    if application.status != ApplicationStatus.OFFER_MADE:
        raise _conflict("application is not waiting for offer acceptance")

    offer = session.get(Offer, offer_id)
    if offer is None or offer.application_id != application.id:
        raise apperr.ERR_NOT_FOUND
    if offer.status != "offered":
        raise _conflict("offer is not active")
    if offer.expires_at is not None and _aware(offer.expires_at) <= _now():
        offer.status = "expired"
        _transition(
            session,
            application,
            ApplicationStatus.OFFER_EXPIRED,
            actor_id=user.id,
            payload={"offer_id": offer.id},
        )
        raise _conflict("offer expired")

    offer.status = "accepted"
    _transition(
        session,
        application,
        ApplicationStatus.OFFER_ACCEPTED,
        actor_id=user.id,
        payload={"offer_id": offer.id},
    )
    evaluation = (
        session.get(Evaluation, offer.evaluation_id)
        if offer.evaluation_id is not None
        else None
    )
    return AcceptOfferResponse(
        status=application.status,
        offer=_offer_out(
            offer,
            {evaluation.id: evaluation} if evaluation is not None else {},
        ),
    )


def decline_offer(
    session: Session,
    user: User,
    application_id: int,
    offer_id: int,
) -> DeclineOfferResponse:
    application = _client_application(session, user, application_id)
    if application.status != ApplicationStatus.OFFER_MADE:
        raise _conflict("application is not waiting for an offer decision")

    offer = session.get(Offer, offer_id)
    if offer is None or offer.application_id != application.id:
        raise apperr.ERR_NOT_FOUND
    if offer.status != "offered":
        raise _conflict("offer is not active")
    if offer.expires_at is not None and _aware(offer.expires_at) <= _now():
        offer.status = "expired"
        _transition(
            session,
            application,
            ApplicationStatus.OFFER_EXPIRED,
            actor_id=user.id,
            payload={"offer_id": offer.id},
        )
        raise _conflict("offer expired")

    offer.status = "declined"
    _transition(
        session,
        application,
        ApplicationStatus.OFFER_DECLINED,
        actor_id=user.id,
        payload={"offer_id": offer.id},
    )
    evaluation = (
        session.get(Evaluation, offer.evaluation_id)
        if offer.evaluation_id is not None
        else None
    )
    return DeclineOfferResponse(
        status=application.status,
        offer=_offer_out(
            offer,
            {evaluation.id: evaluation} if evaluation is not None else {},
        ),
    )


def withdraw_application(
    session: Session,
    user: User,
    application_id: int,
) -> WithdrawResponse:
    application = _client_application(session, user, application_id)
    if ApplicationStatus.WITHDRAWN not in _ALLOWED_TRANSITIONS.get(application.status, set()):
        raise _conflict("application cannot be withdrawn")

    _transition(session, application, ApplicationStatus.WITHDRAWN, actor_id=user.id)
    return WithdrawResponse(id=application.id, status=application.status)


def make_request_hash(method: str, path: str, payload: Any) -> str:
    raw = json.dumps(
        {"method": method, "path": path, "payload": payload},
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_idempotent_response(
    session: Session,
    key: str,
    request_hash: str,
) -> dict[str, Any] | None:
    record = session.scalar(select(IdempotencyKey).where(IdempotencyKey.key == key))
    if record is None:
        return None
    if record.request_hash != request_hash:
        raise _conflict("idempotency key reused with a different request")
    return record.response_body


def save_idempotent_response(
    session: Session,
    key: str,
    request_hash: str,
    response_body: dict[str, Any],
) -> None:
    session.add(
        IdempotencyKey(
            key=key,
            request_hash=request_hash,
            response_body=response_body,
        )
    )
    session.commit()


def _transition(
    session: Session,
    application: Application,
    to_status: ApplicationStatus,
    *,
    actor_id: int | None = None,
    payload: dict[str, Any] | None = None,
    event_type: str | None = None,
) -> None:
    allowed = _ALLOWED_TRANSITIONS.get(application.status, set())
    if to_status not in allowed:
        raise _conflict(
            f"invalid transition {application.status.value} -> {to_status.value}"
        )

    emails = _client_emails(session, application.company_id)
    from_status = application.status
    application.status = to_status
    session.add(
        ApplicationEvent(
            application_id=application.id,
            event_type=event_type or to_status.value,
            from_status=from_status,
            to_status=to_status,
            actor_id=actor_id,
            payload=payload or {},
        )
    )
    session.commit()

    for email in emails:
        send_status_change_email(email, application.id, to_status)


def _add_check(
    session: Session,
    application_id: int,
    *,
    check_type: str,
    status: str,
    source: str,
    fixture_id: str,
) -> None:
    session.add(
        CheckResult(
            application_id=application_id,
            check_type=check_type,
            status=status,
            source=source,
            fixture_id=fixture_id,
        )
    )


def _client_company_id(session: Session, user: User) -> int:
    membership = session.scalar(
        select(CompanyMembership)
        .where(
            CompanyMembership.user_id == user.id,
            CompanyMembership.is_confirmed.is_(True),
        )
        .order_by(CompanyMembership.id)
    )
    if membership is None:
        raise apperr.ERR_FORBIDDEN
    return membership.company_id


def _client_application(
    session: Session,
    user: User,
    application_id: int,
) -> Application:
    company_id = _client_company_id(session, user)
    application = session.get(Application, application_id)
    if application is None:
        raise apperr.ERR_NOT_FOUND
    if application.company_id != company_id:
        raise apperr.ERR_FORBIDDEN
    return application


def _client_emails(session: Session, company_id: int) -> list[str]:
    return list(
        session.scalars(
            select(User.email)
            .join(CompanyMembership, CompanyMembership.user_id == User.id)
            .where(
                CompanyMembership.company_id == company_id,
                CompanyMembership.is_confirmed.is_(True),
            )
            .order_by(User.id)
        ).all()
    )


def _revision(session: Session, application: Application) -> ApplicationRevision | None:
    if application.current_revision_id is None:
        return None
    return session.get(ApplicationRevision, application.current_revision_id)


def _revision_data(revision: ApplicationRevision | None) -> dict[str, Any]:
    return dict(revision.data) if revision is not None else {}


def _application_detail(session: Session, application: Application) -> ApplicationDetail:
    revision = _revision(session, application)
    offers = session.scalars(
        select(Offer)
        .where(Offer.application_id == application.id)
        .order_by(Offer.id)
    ).all()
    evaluations = session.scalars(
        select(Evaluation)
        .where(Evaluation.application_id == application.id)
        .order_by(Evaluation.id)
    ).all()
    events = session.scalars(
        select(ApplicationEvent)
        .where(ApplicationEvent.application_id == application.id)
        .order_by(ApplicationEvent.id)
    ).all()

    evaluations_by_id = {evaluation.id: evaluation for evaluation in evaluations}
    offer_outputs = [
        _offer_out(offer, evaluations_by_id) for offer in offers
    ]

    detail = ApplicationDetail.model_validate(application)
    revision_out = RevisionOut.model_validate(revision) if revision else None
    detail.revision = revision_out
    detail.current_revision = revision_out
    detail.offer = offer_outputs[-1] if offer_outputs else None
    detail.offers = offer_outputs
    detail.evaluations = [
        _evaluation_out(evaluation) for evaluation in evaluations
    ]
    detail.events = [EventOut.model_validate(event) for event in events]
    return detail


_PRODUCT_ELIGIBILITY_REASONS = {"PRODUCT_BUSINESS_AGE_REQUIREMENT"}


def _evaluation_out(evaluation: Evaluation) -> EvaluationOut:
    output = EvaluationOut.model_validate(evaluation)
    output.decision_stage = _decision_stage(evaluation)
    return output


def _decision_stage(evaluation: Evaluation) -> str:
    if evaluation.decision == "NEED_INFO" or evaluation.missing_fields:
        return "DATA"

    codes: set[str] = set()
    for reason in evaluation.reason_codes or []:
        code = reason.get("code") if isinstance(reason, dict) else reason
        if isinstance(code, str):
            codes.add(code)

    if codes & _PRODUCT_ELIGIBILITY_REASONS:
        return "PRODUCT_ELIGIBILITY"
    if evaluation.decision == "DECLINED":
        return "RISK"
    if isinstance(evaluation.offer_data, dict) and evaluation.offer_data:
        return "OFFER"
    return "RISK"


def _offer_out(
    offer: Offer,
    evaluations_by_id: dict[int, Evaluation],
) -> OfferOut:
    output = OfferOut.model_validate(offer)
    evaluation = (
        evaluations_by_id.get(offer.evaluation_id)
        if offer.evaluation_id is not None
        else None
    )
    if evaluation is not None and isinstance(evaluation.offer_data, dict):
        dscr = evaluation.offer_data.get("dscr")
        if isinstance(dscr, (int, float)):
            output.dscr = float(dscr)
    return output


def _risk_category(risk: float) -> str:
    if risk < 34:
        return "LOW"
    if risk < 67:
        return "MEDIUM"
    return "HIGH"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _conflict(message: str) -> apperr.AppError:
    return apperr.new(409, "conflict", message)
