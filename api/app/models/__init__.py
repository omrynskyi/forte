"""All models are imported here so Alembic and tests see the full metadata.

The schema is owned by the skeleton. If your task needs a schema change, add ONE new Alembic
migration in your PR (`make migration m="..."`). Never edit an existing migration. If two PRs both
add migrations, the second to merge rebases and re-points `down_revision` (see CLAUDE.md).
"""

from app.models.audit import AuditLog, Notification
from app.models.auth import AuthSession, MagicLinkToken, User
from app.models.base import Base
from app.models.company import BankAccount, Company, Membership, PayPeriod
from app.models.employee import Compensation, Employee, TimeEntry, Timesheet, Withholding
from app.models.payroll import (
    Correction,
    MockPayout,
    PayrollItem,
    PayrollRun,
    Paystub,
    WebhookEvent,
)

__all__ = [
    "AuditLog",
    "AuthSession",
    "BankAccount",
    "Base",
    "Company",
    "Compensation",
    "Correction",
    "Employee",
    "MagicLinkToken",
    "Membership",
    "MockPayout",
    "Notification",
    "PayPeriod",
    "PayrollItem",
    "PayrollRun",
    "Paystub",
    "TimeEntry",
    "Timesheet",
    "User",
    "WebhookEvent",
    "Withholding",
]
