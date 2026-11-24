import uuid
from datetime import date
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from app.schemas.common import AddressIn, AddressOut, ApiModel, BankAccountOut

Ein = Annotated[str, StringConstraints(pattern=r"^\d{2}-?\d{7}$")]  # CO-1


class CompanyCreate(ApiModel):
    legal_name: Annotated[str, StringConstraints(min_length=2, max_length=200)]
    ein: Ein
    address: AddressIn


class CompanyUpdate(ApiModel):
    legal_name: Annotated[str, StringConstraints(min_length=2, max_length=200)] | None = None
    ein: Ein | None = None
    address: AddressIn | None = None


class SetupChecklist(ApiModel):
    company_profile: bool
    funding_account: bool
    pay_schedule: bool
    team_invited: bool  # at least one other member invited
    complete: bool


class CompanyOut(ApiModel):
    id: uuid.UUID
    legal_name: str
    ein_last4: str
    address: AddressOut
    pay_schedule: Literal["biweekly"] | None
    first_pay_date: date | None
    cutoff_lead_days: int
    funding_account: BankAccountOut | None
    setup: SetupChecklist


class PayScheduleIn(ApiModel):
    schedule: Literal["biweekly"] = "biweekly"
    first_pay_date: date  # must be a weekday, at least cutoff_lead_days business days from today
    cutoff_lead_days: Annotated[int, Field(ge=1, le=3)] = 2
