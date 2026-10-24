"""Synchronous email-notification stub."""

from __future__ import annotations

from ..models import ApplicationStatus


def send_status_change_email(
    user_email: str,
    application_id: int,
    new_status: ApplicationStatus | str,
) -> None:
    status = new_status.value if isinstance(new_status, ApplicationStatus) else new_status
    print(f"[EMAIL MOCK] to={user_email} app={application_id} status={status}")
