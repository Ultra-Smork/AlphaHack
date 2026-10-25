"""Pydantic request, response, and ML-contract schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .models import ApplicationStatus


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email", mode="after")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return value.lower()


class LoginResponse(BaseModel):
    access_token: str


class QuestionnaireData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: int = Field(gt=0, le=1_000_000_000)
    term_months: int = Field(ge=1, le=120)
    company_age_months: int = Field(ge=0, le=1200)
    monthly_revenue: float | None = Field(default=None, ge=0)
    monthly_cash_available_for_debt_service_rub: float | None = None
    revenue_cv_12m: float | None = Field(default=None, ge=0, le=10)
    largest_customer_share: float | None = Field(default=None, ge=0, le=1)
    credit_report_consent_valid: bool = False
    purpose: str | None = Field(default=None, max_length=500)
    has_collateral: bool = False
    existing_debt: float = Field(default=0, ge=0)


class ApplicationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: Literal[1, 2] = 1
    data: QuestionnaireData


class ApplicationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(gt=0)
    data: QuestionnaireData


class RevisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    version: int
    data: QuestionnaireData
    created_at: datetime


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    event_type: str
    from_status: ApplicationStatus | None
    to_status: ApplicationStatus
    actor_id: int | None
    payload: dict[str, object]
    created_at: datetime


class ApplicationSummary(BaseModel):
    id: int
    company_id: int
    product_id: int
    status: ApplicationStatus
    current_revision_id: int | None
    current_revision: RevisionOut | None = None
    amount: int | None = None
    term_months: int | None = None
    created_at: datetime


class ApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    product_id: int
    status: ApplicationStatus
    current_revision_id: int | None
    created_at: datetime


class OfferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    evaluation_id: int | None
    amount: float
    term: int
    rate: float
    payment: float
    dscr: float | None = None
    expires_at: datetime | None
    status: str


class ReasonOut(BaseModel):
    code: str
    text: str
    details: dict[str, str] | None = None


class EvaluationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    decision: str
    decision_stage: Literal[
        "DATA", "PRODUCT_ELIGIBILITY", "RISK", "OFFER"
    ] | None = None
    risk_score: float
    risk_category: str | None
    reason_codes: list[ReasonOut | str]
    risk_details: dict[str, object] | None = None
    missing_fields: list[str] = Field(default_factory=list)
    next_action: str | None = None
    engine_version: str
    policy_version: str


class ApplicationDetail(ApplicationOut):
    revision: RevisionOut | None = None
    current_revision: RevisionOut | None = None
    offer: OfferOut | None = None
    offers: list[OfferOut] = Field(default_factory=list)
    evaluations: list[EvaluationOut] = Field(default_factory=list)
    events: list[EventOut] = Field(default_factory=list)


class AcceptOfferResponse(BaseModel):
    status: ApplicationStatus
    offer: OfferOut


class DeclineOfferResponse(BaseModel):
    status: ApplicationStatus
    offer: OfferOut


class WithdrawResponse(BaseModel):
    id: int
    status: ApplicationStatus


class MLRequest(BaseModel):
    application_id: int
    revision_id: int
    revision_version: int
    product_id: int
    amount: int
    term_months: int
    company_age_months: int
    monthly_revenue: float | None = None
    monthly_cash_available_for_debt_service_rub: float | None = None
    revenue_cv_12m: float | None = None
    largest_customer_share: float | None = None
    credit_report_consent_valid: bool = False
    purpose: str | None = None
    has_collateral: bool = False
    existing_debt: float = 0


class MLOffer(BaseModel):
    amount: float
    term: int
    annual_rate: float
    monthly_payment_rub: float
    dscr: float
    repayment_type: str = "ANNUITY"
    fees_rub: float = 0
    insurance_rub: float = 0
    collateral_required: bool = False


class MLEvaluation(BaseModel):
    decision: Literal["APPROVED", "COUNTEROFFER", "NEED_INFO", "DECLINED"]
    risk_score: float = Field(ge=0, le=100)
    risk_band: str | None = None
    risk_details: dict[str, object] = Field(default_factory=dict)
    offer: MLOffer | None = None
    reason_codes: list[str] = Field(default_factory=list)
    reasons: list[ReasonOut] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    next_action: str | None = None
    engine_version: str
    policy_version: str
