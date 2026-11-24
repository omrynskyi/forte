"""Shared API shapes. Conventions (see docs/ARCHITECTURE.md#api-conventions):
- Money is always `*_cents: int`. Never a float, never a formatted string.
- Hours are `*_minutes: int`.
- Dates are ISO `date`; instants are ISO `datetime` in UTC.
- Sensitive numbers are masked as `*_last4`; full values only via the audited reveal endpoint.
"""

import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models.enums import AccountType, BankAccountStatus

Cents = Annotated[int, Field(description="Integer cents. $12.34 is 1234.")]
NonNegCents = Annotated[int, Field(ge=0, description="Integer cents, >= 0.")]
Digits9 = Annotated[str, StringConstraints(pattern=r"^\d{9}$")]
Zip = Annotated[str, StringConstraints(pattern=r"^\d{5}(-\d{4})?$")]


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ErrorDetail(ApiModel):
    code: str
    message: str


class ErrorOut(ApiModel):
    detail: ErrorDetail


class AddressIn(ApiModel):
    line1: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    line2: str | None = None
    city: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    state: Annotated[str, StringConstraints(pattern=r"^CA$")] = "CA"  # California only
    zip: Zip


class AddressOut(ApiModel):
    line1: str
    line2: str | None
    city: str
    state: str
    zip: str


class BankAccountIn(ApiModel):
    routing_number: Digits9
    account_number: Annotated[str, StringConstraints(pattern=r"^\d{4,17}$")]
    account_type: AccountType = AccountType.CHECKING


class BankAccountOut(ApiModel):
    id: uuid.UUID
    routing_number: str
    account_last4: str
    account_type: AccountType
    status: BankAccountStatus
    verified_at: datetime | None
    failure_reason: str | None = None


class PersonRef(ApiModel):
    id: uuid.UUID
    name: str


class PayPeriodOut(ApiModel):
    id: uuid.UUID
    start_date: date
    end_date: date
    pay_date: date
    cutoff_at: datetime
    regular_run_id: uuid.UUID | None = None
    regular_run_state: str | None = None
