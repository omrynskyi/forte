"""TaxProvider interface (D5, D6, RUN-2). Payroll code gets taxes ONLY through this interface.

The shapes mirror what an embedded-payroll vendor's tax API takes and returns, so a real vendor
is a new class + a config value, with no change to payroll code. Batch call on purpose (NFR-13).
"""

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from app.models.enums import CaFilingStatus, FedFilingStatus


@dataclass(frozen=True)
class TaxRequest:
    employee_id: uuid.UUID
    pay_date: date
    gross_cents: int
    pay_periods_per_year: int
    fed_filing_status: FedFilingStatus
    fed_multiple_jobs: bool
    fed_dependents_cents: int  # annual (W-4 Step 3)
    fed_extra_cents: int  # per paycheck
    ca_filing_status: CaFilingStatus
    ca_allowances: int
    ca_extra_cents: int  # per paycheck


@dataclass(frozen=True)
class TaxResult:
    employee_id: uuid.UUID
    # withheld from the employee
    fed_income_tax_cents: int
    social_security_cents: int
    medicare_cents: int
    ca_pit_cents: int
    ca_sdi_cents: int
    # paid by the employer
    employer_social_security_cents: int
    employer_medicare_cents: int
    futa_cents: int
    ca_sui_cents: int
    ca_ett_cents: int
    calculation_ref: str

    @property
    def employee_taxes_cents(self) -> int:
        return (
            self.fed_income_tax_cents
            + self.social_security_cents
            + self.medicare_cents
            + self.ca_pit_cents
            + self.ca_sdi_cents
        )

    @property
    def employer_taxes_cents(self) -> int:
        return (
            self.employer_social_security_cents
            + self.employer_medicare_cents
            + self.futa_cents
            + self.ca_sui_cents
            + self.ca_ett_cents
        )


class TaxProviderError(Exception):
    """Provider unavailable. Callers leave the run in its current state and let the user retry
    (NFR-14)."""


class TaxProvider(Protocol):
    def calculate(self, requests: list[TaxRequest]) -> list[TaxResult]:
        """Same order as `requests`. Deterministic: same input, same cents."""
        ...
