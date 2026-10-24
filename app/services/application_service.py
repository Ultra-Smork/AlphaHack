"""Credit application FSM, access checks, and idempotency helpers."""

from __future__ import annotations

import hashlib
import json
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
    Company,
    CompanyMembership,
    Contract,
    Disbursement,
    Evaluation,
    IdempotencyKey,
    ManualReview,
    Offer,
    User,
)
from ..platform.ai.ml_client import MLClient
from ..schemas import (
    AcceptOfferResponse,
    ApplicationCreate,
    ApplicationDetail,
    ApplicationSummary,
    ApplicationUpdate,
    BankQueueItem,
    ContractOut,
    DisbursementOut,
    EventOut,
    MLEvaluation,
    MLRequest,
    OfferOut,
    QuestionnaireData,
    ReviewResponse,
    RevisionOut,
    SignResponse,
    WithdrawResponse,
)
from .notification_service import send_status_change_email

CLIENT_ROLE = "client"
BANK_ROLE = "bank"
OFFER_TTL_DAYS = 7
MANUAL_OFFER_RATE = 20.0

_ALLOWED_TRANSITIONS: dict[ApplicationStatus, set[ApplicationStatus]] = {
    ApplicationStatus.DRAFT: {ApplicationStatus.SUBMITTED, ApplicationStatus.WITHDRAWN},
    ApplicationStatus.SUBMITTED: {ApplicationStatus.INTAKE_CHECK, ApplicationStatus.WITHDRAWN},
    ApplicationStatus.INTAKE_CHECK: {
        ApplicationStatus.ENRICHMENT,
        ApplicationStatus.NEEDS_INFO,
        ApplicationStatus.REJECTED,
        ApplicationStatus.WITHDRAWN,
    },
    ApplicationStatus.NEEDS_INFO: {ApplicationStatus.WITHDRAWN},
    ApplicationStatus.ENRICHMENT: {
        ApplicationStatus.SCORING,
        ApplicationStatus.NEEDS_INFO,
        ApplicationStatus.REJECTED,
        ApplicationStatus.WITHDRAWN,
    },
    ApplicationStatus.SCORING: {
        ApplicationStatus.OFFER_MADE,
        ApplicationStatus.NEEDS_INFO,
        ApplicationStatus.MANUAL_REVIEW,
        ApplicationStatus.REJECTED,
        ApplicationStatus.WITHDRAWN,
    },
    ApplicationStatus.MANUAL_REVIEW: {
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
    ApplicationStatus.OFFER_ACCEPTED: {
        ApplicationStatus.SIGNING,
        ApplicationStatus.WITHDRAWN,
    },
    ApplicationStatus.SIGNING: {
        ApplicationStatus.SIGNED,
        ApplicationStatus.WITHDRAWN,
    },
    ApplicationStatus.SIGNED: {
        ApplicationStatus.DISBURSING,
        ApplicationStatus.WITHDRAWN,
    },
    ApplicationStatus.DISBURSING: {
        ApplicationStatus.DISBURSED,
        ApplicationStatus.DISBURSEMENT_FAILED,
    },
}


def list_client_applications(session: Session, user: User) -> list[ApplicationSummary]:
    _require_role(user, CLIENT_ROLE)
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
    _require_role(user, CLIENT_ROLE)
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
    if application.status != ApplicationStatus.DRAFT:
        raise _conflict("only DRAFT applications can be edited")

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
            from_status=ApplicationStatus.DRAFT,
            to_status=ApplicationStatus.DRAFT,
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
    if application.status != ApplicationStatus.DRAFT:
        raise _conflict("only DRAFT applications can be submitted")

    revision = _revision(session, application)
    if revision is None:
        raise _conflict("application has no current revision")
    data = QuestionnaireData.model_validate(revision.data)

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
    if completeness == "needs_info":
        _transition(session, application, ApplicationStatus.NEEDS_INFO)
        return _application_detail(session, application)

    stop_factor = data.company_age_months < 6 or data.amount > 10_000_000
    _add_check(
        session,
        application.id,
        check_type="STOP_FACTOR",
        status="failed" if stop_factor else "passed",
        source="mock",
        fixture_id="fixture:stop-factor:v1",
    )
    if stop_factor:
        _transition(session, application, ApplicationStatus.REJECTED)
        return _application_detail(session, application)

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

    ml_payload = MLRequest(
        application_id=application.id,
        revision_id=revision.id,
        product_id=application.product_id,
        amount=data.amount,
        term_months=data.term_months,
        company_age_months=data.company_age_months,
        monthly_revenue=data.monthly_revenue,
        purpose=data.purpose,
        has_collateral=data.has_collateral,
        existing_debt=data.existing_debt,
    )

    try:
        raw = await ml_client.evaluate(ml_payload.model_dump(mode="json"))
        evaluation_result = MLEvaluation.model_validate(raw)
    except Exception as exc:
        raise apperr.wrap(
            apperr.new(502, "ml_error", "evaluation service failed"), exc
        ) from exc

    evaluation = Evaluation(
        application_id=application.id,
        revision_id=revision.id,
        decision=evaluation_result.decision,
        risk_score=evaluation_result.risk,
        risk_category=_risk_category(evaluation_result.risk),
        offer_data=evaluation_result.offer.model_dump(mode="json") if evaluation_result.offer else {},
        reason_codes=list(evaluation_result.reason_codes),
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
    elif evaluation_result.decision == "MANUAL_REVIEW":
        _transition(
            session,
            application,
            ApplicationStatus.MANUAL_REVIEW,
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
    return AcceptOfferResponse(
        status=application.status,
        offer=OfferOut.model_validate(offer),
    )


def sign_application(session: Session, user: User, application_id: int) -> SignResponse:
    application = _client_application(session, user, application_id)
    if application.status != ApplicationStatus.OFFER_ACCEPTED:
        raise _conflict("application is not ready for signing")

    offer = session.scalar(
        select(Offer)
        .where(
            Offer.application_id == application.id,
            Offer.status == "accepted",
        )
        .order_by(Offer.id.desc())
    )
    if offer is None:
        raise _conflict("accepted offer not found")

    _transition(
        session,
        application,
        ApplicationStatus.SIGNING,
        actor_id=user.id,
        payload={"offer_id": offer.id},
    )

    contract = Contract(
        application_id=application.id,
        offer_id=offer.id,
        status="signed",
        signed_at=_now(),
    )
    session.add(contract)
    session.flush()
    _transition(
        session,
        application,
        ApplicationStatus.SIGNED,
        actor_id=user.id,
        payload={"contract_id": contract.id},
    )
    _transition(
        session,
        application,
        ApplicationStatus.DISBURSING,
        payload={"contract_id": contract.id},
    )

    disbursement = Disbursement(
        application_id=application.id,
        status="success",
        amount=offer.amount,
    )
    session.add(disbursement)
    session.flush()
    _transition(
        session,
        application,
        ApplicationStatus.DISBURSED,
        payload={"disbursement_id": disbursement.id},
    )

    return SignResponse(
        status=application.status,
        contract=ContractOut.model_validate(contract),
        disbursement=DisbursementOut.model_validate(disbursement),
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


def bank_queue(session: Session, user: User) -> list[BankQueueItem]:
    _require_role(user, BANK_ROLE)

    rows = session.execute(
        select(Application, Company, ApplicationRevision)
        .join(Company, Company.id == Application.company_id)
        .outerjoin(
            ApplicationRevision,
            ApplicationRevision.id == Application.current_revision_id,
        )
        .where(Application.status == ApplicationStatus.MANUAL_REVIEW)
        .order_by(Application.id)
    ).all()

    result: list[BankQueueItem] = []
    for application, company, revision in rows:
        data = _revision_data(revision)
        result.append(
            BankQueueItem(
                id=application.id,
                company_id=application.company_id,
                company_name=company.name,
                product_id=application.product_id,
                status=application.status,
                amount=data.get("amount"),
                term_months=data.get("term_months"),
                company_age_months=data.get("company_age_months"),
                created_at=application.created_at,
            )
        )
    return result


def review_application(
    session: Session,
    user: User,
    application_id: int,
    decision: str,
    reason: str | None,
) -> ReviewResponse:
    _require_role(user, BANK_ROLE)

    application = session.get(Application, application_id)
    if application is None:
        raise apperr.ERR_NOT_FOUND
    if application.status != ApplicationStatus.MANUAL_REVIEW:
        raise _conflict("application is not in manual review")

    review = ManualReview(
        application_id=application.id,
        underwriter_id=user.id,
        decision=decision,
        reason=reason,
    )
    session.add(review)
    session.flush()

    offer: Offer | None = None
    if decision == "APPROVE":
        revision = _revision(session, application)
        if revision is None:
            raise _conflict("application has no current revision")
        data = QuestionnaireData.model_validate(revision.data)
        offer = Offer(
            application_id=application.id,
            evaluation_id=None,
            amount=float(data.amount),
            term=data.term_months,
            rate=MANUAL_OFFER_RATE,
            payment=_annuity(float(data.amount), MANUAL_OFFER_RATE, data.term_months),
            expires_at=_now() + timedelta(days=OFFER_TTL_DAYS),
            status="offered",
        )
        session.add(offer)
        session.flush()
        _transition(
            session,
            application,
            ApplicationStatus.OFFER_MADE,
            actor_id=user.id,
            payload={"manual_review_id": review.id, "offer_id": offer.id},
        )
    elif decision == "REJECT":
        _transition(
            session,
            application,
            ApplicationStatus.REJECTED,
            actor_id=user.id,
            payload={"manual_review_id": review.id, "reason": reason},
        )
    else:
        _transition(
            session,
            application,
            ApplicationStatus.NEEDS_INFO,
            actor_id=user.id,
            payload={"manual_review_id": review.id, "reason": reason},
        )

    return ReviewResponse(
        application_id=application.id,
        status=application.status,
        manual_review_id=review.id,
        offer=OfferOut.model_validate(offer) if offer else None,
    )


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


def _require_role(user: User, role: str) -> None:
    if user.role != role:
        raise apperr.ERR_FORBIDDEN


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
    _require_role(user, CLIENT_ROLE)
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
                User.role == CLIENT_ROLE,
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
    offer = session.scalar(
        select(Offer)
        .where(Offer.application_id == application.id)
        .order_by(Offer.id.desc())
    )
    events = session.scalars(
        select(ApplicationEvent)
        .where(ApplicationEvent.application_id == application.id)
        .order_by(ApplicationEvent.id)
    ).all()

    detail = ApplicationDetail.model_validate(application)
    detail.revision = RevisionOut.model_validate(revision) if revision else None
    detail.offer = OfferOut.model_validate(offer) if offer else None
    detail.events = [EventOut.model_validate(event) for event in events]
    return detail


def _risk_category(risk: float) -> str:
    if risk < 0.34:
        return "low"
    if risk < 0.67:
        return "medium"
    return "high"


def _annuity(amount: float, annual_rate: float, term_months: int) -> float:
    monthly_rate = annual_rate / 100 / 12
    if monthly_rate == 0:
        return round(amount / term_months, 2)
    payment = amount * monthly_rate / (1 - (1 + monthly_rate) ** -term_months)
    return round(payment, 2)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _conflict(message: str) -> apperr.AppError:
    return apperr.new(409, "conflict", message)
