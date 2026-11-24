import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Cents, CompanyScoped, IdMixin, enum_col
from app.models.enums import CorrectionReason, PayoutStatus, PayType, RunState, RunType


class PayrollRun(IdMixin, CompanyScoped, Base):
    """State changes ONLY through app.payroll.state_machine.transition() (D7, NFR-4)."""

    __tablename__ = "payroll_runs"

    run_type: Mapped[RunType] = mapped_column(enum_col(RunType))
    state: Mapped[RunState] = mapped_column(enum_col(RunState), default=RunState.DRAFT)
    pay_period_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pay_periods.id"))
    pay_date: Mapped[date]
    original_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("payroll_runs.id"))

    created_by_membership_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("memberships.id"))
    submitted_by_membership_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("memberships.id")
    )
    approved_by_membership_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("memberships.id")
    )
    cancelled_by_membership_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("memberships.id")
    )
    submitted_at: Mapped[datetime | None]
    approved_at: Mapped[datetime | None]
    cancelled_at: Mapped[datetime | None]
    processing_at: Mapped[datetime | None]
    paid_at: Mapped[datetime | None]
    failed_at: Mapped[datetime | None]
    failure_reason: Mapped[str | None] = mapped_column(Text)
    calculated_at: Mapped[datetime | None]

    # NFR-3: generated once at creation and reused on every payout retry.
    idempotency_key: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, default=uuid.uuid4
    )
    provider_payout_id: Mapped[str | None] = mapped_column(String(100))

    # NFR-2: always equal to the sum of the run's items. Recomputed with the items, never by hand.
    total_gross_cents: Mapped[int] = mapped_column(Cents, default=0)
    total_employee_taxes_cents: Mapped[int] = mapped_column(Cents, default=0)
    total_deductions_cents: Mapped[int] = mapped_column(Cents, default=0)
    total_net_cents: Mapped[int] = mapped_column(Cents, default=0)
    total_employer_taxes_cents: Mapped[int] = mapped_column(Cents, default=0)
    total_company_cost_cents: Mapped[int] = mapped_column(Cents, default=0)

    __table_args__ = (
        # At most one live regular run per pay period.
        Index(
            "uq_payroll_runs_one_regular_per_period",
            "pay_period_id",
            unique=True,
            postgresql_where=text("run_type = 'regular' AND state <> 'cancelled'"),
        ),
        CheckConstraint(
            "(run_type = 'regular') = (pay_period_id IS NOT NULL)", name="regular_has_period"
        ),
    )


class PayrollItem(IdMixin, CompanyScoped, Base):
    """One employee's line in a run. A DB trigger (migration 0001) rejects INSERT/UPDATE/DELETE
    unless the parent run is in DRAFT, so items are immutable after submit (RUN-4)."""

    __tablename__ = "payroll_items"

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payroll_runs.id"), index=True)
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"), index=True)
    pay_type: Mapped[PayType] = mapped_column(enum_col(PayType))
    minutes: Mapped[int | None] = mapped_column(Integer)  # hourly: minutes paid
    rate_cents: Mapped[int] = mapped_column(Cents)  # hourly rate, or the period salary
    memo: Mapped[str | None] = mapped_column(Text)  # e.g. "Correction: 6.5 missed hours on Oct 30"

    gross_cents: Mapped[int] = mapped_column(Cents)
    # Employee taxes (withheld)
    fed_income_tax_cents: Mapped[int] = mapped_column(Cents, default=0)
    social_security_cents: Mapped[int] = mapped_column(Cents, default=0)
    medicare_cents: Mapped[int] = mapped_column(Cents, default=0)
    ca_pit_cents: Mapped[int] = mapped_column(Cents, default=0)
    ca_sdi_cents: Mapped[int] = mapped_column(Cents, default=0)
    deductions_cents: Mapped[int] = mapped_column(Cents, default=0)  # always 0 in the MVP
    net_cents: Mapped[int] = mapped_column(Cents)
    # Employer taxes (company cost, not withheld)
    employer_social_security_cents: Mapped[int] = mapped_column(Cents, default=0)
    employer_medicare_cents: Mapped[int] = mapped_column(Cents, default=0)
    futa_cents: Mapped[int] = mapped_column(Cents, default=0)
    ca_sui_cents: Mapped[int] = mapped_column(Cents, default=0)
    ca_ett_cents: Mapped[int] = mapped_column(Cents, default=0)
    employer_cost_cents: Mapped[int] = mapped_column(Cents)  # gross + employer taxes

    bank_account_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bank_accounts.id"))
    tax_calculation_ref: Mapped[str | None] = mapped_column(String(100))

    __table_args__ = (
        UniqueConstraint("run_id", "employee_id", name="uq_payroll_items_run_employee"),
        CheckConstraint(
            "net_cents = gross_cents - fed_income_tax_cents - social_security_cents"
            " - medicare_cents - ca_pit_cents - ca_sdi_cents - deductions_cents",
            name="net_is_gross_minus_withholding",
        ),
        CheckConstraint(
            "employer_cost_cents = gross_cents + employer_social_security_cents"
            " + employer_medicare_cents + futa_cents + ca_sui_cents + ca_ett_cents",
            name="employer_cost_is_gross_plus_employer_taxes",
        ),
    )


class Paystub(IdMixin, CompanyScoped, Base):
    """Created when a run becomes PAID. Before that, the API serves a preview straight from the
    PayrollItem (PAY-2). In the API, a paystub is always addressed by its payroll_item_id.

    The PDF (PAY-3) is rendered ONCE, right after the run reaches PAID, stored in object storage
    (S3 / MinIO bucket `forte-paystubs`, versioned), and never regenerated: a paystub is a legal
    record, so a later template or tax change must not alter a stub the employee already received.
    `pdf_object_key` is set-once; a DB trigger (migration 0001) rejects changing it after it is set.
    Key format: companies/<company_id>/paystubs/<paystub_id>.pdf
    """

    __tablename__ = "paystubs"

    payroll_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payroll_items.id"), unique=True)
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"), index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payroll_runs.id"))
    pay_date: Mapped[date]
    issued_at: Mapped[datetime]
    pdf_object_key: Mapped[str | None] = mapped_column(String(300))  # NULL until rendered+stored
    pdf_sha256: Mapped[str | None] = mapped_column(String(64))  # integrity check of stored bytes
    pdf_version_id: Mapped[str | None] = mapped_column(String(200))  # S3 version id (versioning)
    pdf_rendered_at: Mapped[datetime | None]


class Correction(IdMixin, CompanyScoped, Base):
    """COR-1. Status is NOT stored: it is derived from the correction run's state
    (see app/payroll/states.py::correction_status)."""

    __tablename__ = "corrections"

    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"), index=True)
    original_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payroll_items.id"), index=True)
    correction_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payroll_runs.id"), unique=True)
    reason: Mapped[CorrectionReason] = mapped_column(enum_col(CorrectionReason))
    missed_minutes: Mapped[int] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)
    created_by_membership_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("memberships.id"))

    __table_args__ = (CheckConstraint("missed_minutes > 0", name="positive_minutes"),)


class WebhookEvent(IdMixin, Base):
    """Dedupes incoming provider webhooks: a replayed event_id is acknowledged and ignored."""

    __tablename__ = "webhook_events"

    provider: Mapped[str] = mapped_column(String(40))
    event_id: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict] = mapped_column(JSONB)
    processed_at: Mapped[datetime | None]

    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_webhook_events_event"),)


class MockPayout(IdMixin, Base):
    """State of the MOCK payments provider only (adapters/mock/payments.py). A real provider keeps
    this on its side. Unique idempotency_key is what makes a replayed payout a no-op (NFR-3)."""

    __tablename__ = "mock_payouts"

    idempotency_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    provider_payout_id: Mapped[str] = mapped_column(String(100), unique=True)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    amount_cents: Mapped[int] = mapped_column(Cents)
    status: Mapped[PayoutStatus] = mapped_column(enum_col(PayoutStatus))
    callback_sent_at: Mapped[datetime | None]
