import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import Field

from app.schemas.common import ApiModel, Cents


class CorrectionIn(ApiModel):
    original_item_id: uuid.UUID  # the paid paystub that was wrong
    reason: Literal["missed_hours"] = "missed_hours"  # D11
    missed_minutes: Annotated[int, Field(gt=0, le=14 * 1440)]
    note: str | None = None


class CorrectionPreview(ApiModel):
    """What the Mgr-Correction screen shows before submitting."""

    employee_name: str
    original_pay_date: date
    original_minutes: int | None
    rate_cents: Cents  # from the original item; not editable
    gross_cents: Cents
    employee_taxes_cents: Cents
    net_cents: Cents


class CorrectionOut(ApiModel):
    id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str
    original_item_id: uuid.UUID
    original_run_id: uuid.UUID
    original_pay_date: date
    correction_run_id: uuid.UUID
    reason: str
    missed_minutes: int
    rate_cents: Cents
    gross_cents: Cents
    net_cents: Cents
    status: Literal["opened", "in_review", "approved", "paid", "cancelled"]
    note: str | None
    created_at: datetime
