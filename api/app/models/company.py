import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CompanyScoped, IdMixin, enum_col
from app.models.enums import (
    AccountType,
    BankAccountStatus,
    BankOwnerType,
    MembershipStatus,
    PaySchedule,
    Role,
)
from app.security.crypto import EncryptedString


class Company(IdMixin, Base):
    __tablename__ = "companies"

    legal_name: Mapped[str] = mapped_column(String(200))
    ein: Mapped[str] = mapped_column(EncryptedString(255))  # 9 digits, encrypted (CO-1)
    ein_last4: Mapped[str] = mapped_column(String(4))
    address_line1: Mapped[str] = mapped_column(String(200))
    address_line2: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(2), default="CA")
    zip: Mapped[str] = mapped_column(String(10))

    pay_schedule: Mapped[PaySchedule | None] = mapped_column(enum_col(PaySchedule))
    first_pay_date: Mapped[date | None]
    # Cutoff = pay_date minus this many business days, at 17:00 America/Los_Angeles.
    cutoff_lead_days: Mapped[int] = mapped_column(Integer, default=2)
    setup_completed_at: Mapped[datetime | None]

    __table_args__ = (
        CheckConstraint("state = 'CA'", name="california_only"),
        CheckConstraint("cutoff_lead_days BETWEEN 1 AND 3", name="cutoff_lead_days_range"),
    )


class Membership(IdMixin, CompanyScoped, Base):
    """Links a User to a Company with a role. One company per user in the MVP (D3)."""

    __tablename__ = "memberships"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True)
    role: Mapped[Role] = mapped_column(enum_col(Role))
    status: Mapped[MembershipStatus] = mapped_column(
        enum_col(MembershipStatus), default=MembershipStatus.INVITED
    )
    # Set when this member is also on payroll (every Employee; optionally Admins/PMs).
    employee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("employees.id"), unique=True)
    invited_by_membership_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("memberships.id"))


class BankAccount(IdMixin, CompanyScoped, Base):
    """Company funding account or employee direct deposit. Never updated in place except status:
    a change creates a new row and marks the old one REPLACED."""

    __tablename__ = "bank_accounts"

    owner_type: Mapped[BankOwnerType] = mapped_column(enum_col(BankOwnerType))
    employee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("employees.id"), index=True)
    routing_number: Mapped[str] = mapped_column(String(9))
    account_number: Mapped[str] = mapped_column(EncryptedString(255))
    account_last4: Mapped[str] = mapped_column(String(4))
    account_type: Mapped[AccountType] = mapped_column(enum_col(AccountType))
    status: Mapped[BankAccountStatus] = mapped_column(
        enum_col(BankAccountStatus), default=BankAccountStatus.PENDING
    )
    verified_at: Mapped[datetime | None]
    provider_ref: Mapped[str | None] = mapped_column(String(100))

    __table_args__ = (
        CheckConstraint(
            "(owner_type = 'employee') = (employee_id IS NOT NULL)", name="owner_matches_employee"
        ),
    )


class PayPeriod(IdMixin, CompanyScoped, Base):
    """Generated from the pay schedule (CO-3). See docs/ARCHITECTURE.md#pay-periods for the rule."""

    __tablename__ = "pay_periods"

    start_date: Mapped[date]
    end_date: Mapped[date]
    pay_date: Mapped[date]
    cutoff_at: Mapped[datetime]  # UTC instant of "approve by" (RUN-3, RUN-6)

    __table_args__ = (
        UniqueConstraint("company_id", "start_date", name="uq_pay_periods_company_start"),
    )
