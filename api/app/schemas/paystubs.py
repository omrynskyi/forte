"""Paystubs (PAY-1..3, COR-2). A paystub's id in the API is its payroll_item_id, so previews (no
Paystub row yet) and final stubs share one URL."""

import uuid
from datetime import date, datetime
from typing import Literal

from app.models.enums import PayType, RunType
from app.schemas.common import ApiModel, Cents


class CorrectionBrief(ApiModel):
    id: uuid.UUID
    status: Literal["opened", "in_review", "approved", "paid", "cancelled"]
    reason: str
    missed_minutes: int
    gross_cents: Cents
    correction_item_id: uuid.UUID | None  # the correction's own paystub, once it exists
    created_at: datetime


class PaystubSummary(ApiModel):
    id: uuid.UUID  # payroll_item_id
    run_id: uuid.UUID
    run_type: RunType
    pay_date: date
    is_preview: bool  # True while the run is submitted/approved/processing/failed (PAY-2)
    gross_cents: Cents
    net_cents: Cents
    corrections: list[CorrectionBrief]  # corrections opened against this stub (COR-2)
    corrects_item_id: uuid.UUID | None  # set if this stub IS a correction of another
    pdf_available: bool  # final + stored PDF exists (PAY-3)


class PaystubLine(ApiModel):
    code: str  # "gross" | "fed_income_tax" | "social_security" | "medicare" | "ca_pit" | "ca_sdi"
    label: str  # "Federal income tax"
    amount_cents: Cents
    explanation: str  # one plain-language line from app/paystubs/templates.py (PAY-1)


class PaystubDetail(PaystubSummary):
    period_start: date | None
    period_end: date | None
    employer_name: str
    employer_address: str
    employee_name: str
    employee_number: int
    ssn_last4: str | None
    pay_type: PayType
    minutes: int | None
    rate_cents: Cents
    memo: str | None
    headline: str  # "You earned $1,960.00 for 80.0 hours at $24.50 an hour. ..." (PAY-1)
    earnings: list[PaystubLine]
    taxes: list[PaystubLine]
    employee_taxes_cents: Cents
    deposit_account_last4: str | None


class PaystubPdfLink(ApiModel):
    """PAY-3: short-lived presigned URL to the stored, immutable PDF. Open it right away."""

    url: str
    expires_at: datetime
    filename: str  # e.g. "Forte-paystub-2026-12-11.pdf"
