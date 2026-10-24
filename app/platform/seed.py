"""Idempotent demo data seed."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import hash_password
from ..models import Company, CompanyMembership, User

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
        role="client",
    )
    _ensure_user(
        session,
        email="bank@demo.ru",
        full_name="Банк Демо",
        role="bank",
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
                role="owner",
                permissions=["*"],
                is_confirmed=True,
            )
        )

    session.commit()
    log.info("demo data seeded")


def _ensure_user(
    session: Session,
    *,
    email: str,
    full_name: str,
    role: str,
) -> User:
    user = session.scalar(select(User).where(User.email == email))
    if user is not None:
        return user

    user = User(
        email=email,
        password_hash=hash_password(_DEMO_PASSWORD),
        full_name=full_name,
        role=role,
    )
    session.add(user)
    session.flush()
    return user
