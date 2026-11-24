import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import EmailStr, Field, StringConstraints

from app.models.enums import (
    EmploymentStatus,
    MembershipStatus,
    PayType,
    SeparationType,
)
from app.schemas.common import AddressOut, ApiModel, BankAccountOut, Cents
from app.schemas.me import WithholdingOut

Name = Annotated[str, StringConstraints(min_length=1, max_length=100)]


class CompensationIn(ApiModel):
    pay_type: PayType
    amount_cents: Annotated[int, Field(gt=0)]  # annual salary cents, or cents per hour
    effective_date: date


class CompensationOut(ApiModel):
    id: uuid.UUID
    pay_type: PayType
    amount_cents: Cents
    effective_date: date
    set_by_name: str | None
    created_at: datetime
    is_current: bool


class EmployeeCreate(ApiModel):
    """EMP-1: creates the Employee, its first Compensation, and an EMPLOYEE membership + invite."""

    first_name: Name
    last_name: Name
    email: EmailStr
    job_title: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    hire_date: date
    compensation: CompensationIn


class EmployeeUpdate(ApiModel):
    first_name: Name | None = None
    last_name: Name | None = None
    job_title: Annotated[str, StringConstraints(min_length=1, max_length=120)] | None = None


class EmployeeListItem(ApiModel):
    id: uuid.UUID
    employee_number: int
    name: str
    email: str
    job_title: str
    pay_type: PayType | None
    pay_amount_cents: Cents | None
    status: EmploymentStatus
    membership_status: MembershipStatus | None
    ready: bool
    missing: list[str]  # keys from services/readiness.py MISSING_LABELS


class EmployeeOut(ApiModel):
    id: uuid.UUID
    employee_number: int
    first_name: str
    last_name: str
    email: str
    job_title: str
    hire_date: date
    dob: date | None
    ssn_last4: str | None
    address: AddressOut | None
    status: EmploymentStatus
    end_date: date | None
    separation_type: SeparationType | None
    membership_status: MembershipStatus | None
    role: str | None
    compensation: CompensationOut | None  # current
    withholding: WithholdingOut | None  # current
    deposit_account: BankAccountOut | None  # current verified
    ready: bool
    missing: list[str]


class RevealIn(ApiModel):
    field: Literal["ssn", "bank_account_number"]


class RevealOut(ApiModel):
    field: str
    value: str


class TerminateIn(ApiModel):
    end_date: date
    separation_type: SeparationType
    reason: Annotated[str, StringConstraints(max_length=500)] | None = None


class TerminateOut(ApiModel):
    employee_id: uuid.UUID
    final_run_id: uuid.UUID
    final_pay_due_date: date
    due_date_rule: str  # plain-language CA rule shown in the UI
