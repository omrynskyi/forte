import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import Field

from app.models.enums import TimesheetStatus
from app.schemas.common import ApiModel, PayPeriodOut


class TimeEntryIn(ApiModel):
    work_date: date
    minutes: Annotated[int, Field(ge=0, le=1440)]  # 0 deletes the day


class TimeEntryOut(TimeEntryIn):
    id: uuid.UUID


class TimesheetEntriesPut(ApiModel):
    """Upsert by work_date. Every date must fall inside the timesheet's pay period and be <= today."""

    entries: list[TimeEntryIn]


class TimesheetOut(ApiModel):
    id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str
    pay_period: PayPeriodOut
    status: TimesheetStatus
    entries: list[TimeEntryOut]
    total_minutes: int
    rate_cents: int | None  # current hourly rate, for the manager's view
    review_note: str | None
    reviewed_by_name: str | None
    reviewed_at: datetime | None
    editable: bool  # for the caller


class ReviewIn(ApiModel):
    note: str | None = None  # required (non-empty) when rejecting
