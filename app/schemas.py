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

    amount: int = Field(gt=0)
    term_months: int = Field(ge=6, le=36)
    company_age_months: int = Field(ge=0)
    monthly_revenue: float | None = Field(default=None, ge=0)
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
    expires_at: datetime | None
    status: str


class ApplicationDetail(ApplicationOut):
    revision: RevisionOut | None = None
    offer: OfferOut | None = None
    events: list[EventOut] = Field(default_factory=list)


class AcceptOfferResponse(BaseModel):
    status: ApplicationStatus
    offer: OfferOut


class ContractOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    offer_id: int
    status: str
    signed_at: datetime | None


class DisbursementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    status: str
    amount: float
    created_at: datetime


class SignResponse(BaseModel):
    status: ApplicationStatus
    contract: ContractOut
    disbursement: DisbursementOut


class WithdrawResponse(BaseModel):
    id: int
    status: ApplicationStatus


class BankQueueItem(BaseModel):
    id: int
    company_id: int
    company_name: str
    product_id: int
    status: ApplicationStatus
    amount: int | None
    term_months: int | None
    company_age_months: int | None
    created_at: datetime


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["APPROVE", "REJECT", "NEED_INFO"]
    reason: str | None = Field(default=None, max_length=1000)

    @field_validator("decision", mode="before")
    @classmethod
    def _normalize_decision(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value


class ReviewResponse(BaseModel):
    application_id: int
    status: ApplicationStatus
    manual_review_id: int
    offer: OfferOut | None = None


class MLRequest(BaseModel):
    application_id: int
    revision_id: int
    product_id: int
    amount: int
    term_months: int
    company_age_months: int
    monthly_revenue: float | None = None
    purpose: str | None = None
    has_collateral: bool = False
    existing_debt: float = 0


class MLOffer(BaseModel):
    amount: float
    term: int
    annual_rate: float
    monthly_payment_rub: float
    dscr: float


class MLEvaluation(BaseModel):
    decision: Literal["APPROVED", "COUNTEROFFER", "NEED_INFO", "MANUAL_REVIEW", "DECLINED"]
    risk: float = Field(ge=0, le=1)
    offer: MLOffer | None = None
    reason_codes: list[str] = Field(default_factory=list)
    engine_version: str
    policy_version: str
