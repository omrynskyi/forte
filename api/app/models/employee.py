import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Cents, CompanyScoped, IdMixin, enum_col
from app.models.enums import (
    CaFilingStatus,
    EmploymentStatus,
    FedFilingStatus,
    PayType,
    SeparationType,
    TimesheetStatus,
)
from app.security.crypto import EncryptedString


class Employee(IdMixin, CompanyScoped, Base):
    __tablename__ = "employees"

    employee_number: Mapped[int] = mapped_column(Integer)  # per company, shown as e.g. "LB-0004"
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(320))  # invite / sign-in email
    job_title: Mapped[str] = mapped_column(String(120))  # EMP-4: employees can't change it
    hire_date: Mapped[date]

    # Filled by the employee during onboarding (ONB-1)
    dob: Mapped[date | None]
    ssn: Mapped[str | None] = mapped_column(EncryptedString(255))
    ssn_last4: Mapped[str | None] = mapped_column(String(4))
    address_line1: Mapped[str | None] = mapped_column(String(200))
    address_line2: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(2))
    zip: Mapped[str | None] = mapped_column(String(10))

    status: Mapped[EmploymentStatus] = mapped_column(
        enum_col(EmploymentStatus), default=EmploymentStatus.ACTIVE
    )
    end_date: Mapped[date | None]
    separation_type: Mapped[SeparationType | None] = mapped_column(enum_col(SeparationType))
    termination_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("company_id", "employee_number", name="uq_employees_company_number"),
    )


class Compensation(IdMixin, CompanyScoped, Base):
    """EMP-2: append-only. The current rate is the row with the latest effective_date <= the date
    in question (ties broken by created_at). Never UPDATE or DELETE a row."""

    __tablename__ = "compensations"

    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"))
    pay_type: Mapped[PayType] = mapped_column(enum_col(PayType))
    amount_cents: Mapped[int] = mapped_column(Cents)  # annual salary, or cents per hour
    effective_date: Mapped[date]
    created_by_membership_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("memberships.id"))

    __table_args__ = (
        CheckConstraint("amount_cents > 0", name="positive_amount"),
        Index("ix_compensations_employee_effective", "employee_id", "effective_date"),
    )


class Withholding(IdMixin, CompanyScoped, Base):
    """Simplified W-4 + DE 4 (D6). Versioned like Compensation: append-only, latest effective wins."""

    __tablename__ = "withholdings"

    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"), index=True)
    effective_date: Mapped[date]
    fed_filing_status: Mapped[FedFilingStatus] = mapped_column(enum_col(FedFilingStatus))
    fed_multiple_jobs: Mapped[bool] = mapped_column(default=False)
    fed_dependents_cents: Mapped[int] = mapped_column(Cents, default=0)  # W-4 Step 3, annual
    fed_extra_cents: Mapped[int] = mapped_column(Cents, default=0)  # W-4 Step 4(c), per paycheck
    ca_filing_status: Mapped[CaFilingStatus] = mapped_column(enum_col(CaFilingStatus))
    ca_allowances: Mapped[int] = mapped_column(Integer, default=0)
    ca_extra_cents: Mapped[int] = mapped_column(Cents, default=0)  # per paycheck
    created_by_membership_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("memberships.id"))


class Timesheet(IdMixin, CompanyScoped, Base):
    __tablename__ = "timesheets"

    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"))
    pay_period_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pay_periods.id"), index=True)
    status: Mapped[TimesheetStatus] = mapped_column(
        enum_col(TimesheetStatus), default=TimesheetStatus.OPEN
    )
    reviewed_by_membership_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("memberships.id")
    )
    reviewed_at: Mapped[datetime | None]
    review_note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("employee_id", "pay_period_id", name="uq_timesheets_employee_period"),
    )


class TimeEntry(IdMixin, CompanyScoped, Base):
    """One row per worked day. Hours are integer minutes (0..1440)."""

    __tablename__ = "time_entries"

    timesheet_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("timesheets.id", ondelete="CASCADE"), index=True
    )
    work_date: Mapped[date]
    minutes: Mapped[int] = mapped_column(Integer)

    __table_args__ = (
        CheckConstraint("minutes BETWEEN 0 AND 1440", name="minutes_range"),
        UniqueConstraint("timesheet_id", "work_date", name="uq_time_entries_sheet_date"),
    )
