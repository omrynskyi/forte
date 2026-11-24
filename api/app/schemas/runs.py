import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import Field

from app.models.enums import PayType, RunState, RunType
from app.payroll.states import RunAction
from app.schemas.common import ApiModel, Cents


class BonusItemIn(ApiModel):
    employee_id: uuid.UUID
    amount_cents: Annotated[int, Field(gt=0)]


class RunCreate(ApiModel):
    """Regular: pay_period_id required. Bonus (P1, A-11): pay_date + bonus_items.
    Corrections and final paychecks are created by their own endpoints, not here."""

    run_type: Literal["regular", "bonus"]
    pay_period_id: uuid.UUID | None = None
    pay_date: date | None = None
    bonus_items: list[BonusItemIn] | None = None


class RunTotals(ApiModel):
    gross_cents: Cents
    employee_taxes_cents: Cents
    deductions_cents: Cents
    net_cents: Cents
    employer_taxes_cents: Cents
    company_cost_cents: Cents


class RunSummary(ApiModel):
    id: uuid.UUID
    run_type: RunType
    state: RunState
    pay_date: date
    period_start: date | None
    period_end: date | None
    cutoff_at: datetime | None  # regular runs only
    at_risk: bool  # past cutoff and not yet approved (RUN-6)
    employee_count: int
    totals: RunTotals
    original_run_id: uuid.UUID | None
    created_at: datetime
    submitted_at: datetime | None
    approved_at: datetime | None
    paid_at: datetime | None


class TaxLines(ApiModel):
    fed_income_tax_cents: Cents
    social_security_cents: Cents
    medicare_cents: Cents
    ca_pit_cents: Cents
    ca_sdi_cents: Cents


class EmployerTaxLines(ApiModel):
    social_security_cents: Cents
    medicare_cents: Cents
    futa_cents: Cents
    ca_sui_cents: Cents
    ca_ett_cents: Cents


class RunItemOut(ApiModel):
    id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str
    is_caller: bool  # "(you)" in the design
    pay_type: PayType
    minutes: int | None
    rate_cents: Cents
    gross_cents: Cents
    taxes: TaxLines
    employee_taxes_cents: Cents
    net_cents: Cents
    employer_taxes: EmployerTaxLines
    employer_cost_cents: Cents
    memo: str | None


class RunBlocker(ApiModel):
    """EMP-5: an employee left out of the run, and why."""

    employee_id: uuid.UUID
    employee_name: str
    missing: list[str]


class RunDetail(RunSummary):
    items: list[RunItemOut]
    blockers: list[RunBlocker]
    timesheets_unapproved: int  # hourly employees in the period whose sheet isn't approved
    allowed_actions: list[RunAction]  # filtered for the CALLER's role; drives the UI buttons
    created_by_name: str | None
    submitted_by_name: str | None
    approved_by_name: str | None
    failure_reason: str | None


class TransitionIn(ApiModel):
    note: str | None = None
