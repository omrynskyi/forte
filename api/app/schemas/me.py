"""Employee self-service (ONB-1, ONB-2). Every endpoint acts on the caller's own employee record."""

import uuid
from datetime import date
from typing import Annotated

from pydantic import Field, StringConstraints

from app.models.enums import CaFilingStatus, FedFilingStatus
from app.schemas.common import AddressIn, AddressOut, ApiModel, BankAccountOut, NonNegCents

Ssn = Annotated[str, StringConstraints(pattern=r"^\d{3}-?\d{2}-?\d{4}$")]


class PersonalInfoIn(ApiModel):
    """Onboarding step 1 (Emp-Onboard-1). Legal name is confirmed here."""

    first_name: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    last_name: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    dob: date
    ssn: Ssn
    address: AddressIn


class WithholdingIn(ApiModel):
    """Onboarding step 2 (Emp-Onboard-2). Simplified W-4 + DE 4 (D6)."""

    fed_filing_status: FedFilingStatus
    fed_multiple_jobs: bool = False
    fed_dependents_cents: NonNegCents = 0
    fed_extra_cents: NonNegCents = 0
    ca_filing_status: CaFilingStatus
    ca_allowances: Annotated[int, Field(ge=0, le=20)] = 0
    ca_extra_cents: NonNegCents = 0


class WithholdingOut(WithholdingIn):
    id: uuid.UUID
    effective_date: date


class ProfileOut(ApiModel):
    employee_id: uuid.UUID
    employee_number: int
    first_name: str
    last_name: str
    email: str
    job_title: str
    company_name: str
    dob: date | None
    ssn_last4: str | None
    address: AddressOut | None
    withholding: WithholdingOut | None
    deposit_account: BankAccountOut | None
    is_former: bool
    end_date: date | None


class HomeOut(ApiModel):
    """Emp-Home. `upcoming` is the preview paystub of a submitted run (PAY-2), if any."""

    first_name: str
    company_name: str
    next_pay_date: date | None
    onboarding_complete: bool
    missing: list[str]
    is_hourly: bool
    minutes_this_period: int | None
    upcoming: "PaystubSummary | None"
    recent: list["PaystubSummary"]


from app.schemas.paystubs import PaystubSummary  # noqa: E402

HomeOut.model_rebuild()
