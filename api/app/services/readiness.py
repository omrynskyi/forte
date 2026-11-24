"""EMP-5: who is ready to be paid. Used by onboarding (B-06), the employee list (B-05), the run
builder (A-03, to list blockers) and the dashboard (A-09). Keep this the single definition."""

import uuid
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BankAccount, Compensation, Employee, Withholding
from app.models.enums import BankAccountStatus, BankOwnerType, EmploymentStatus

MISSING_LABELS = {
    "personal_info": "Personal info (SSN, date of birth, address)",
    "withholding": "Tax withholding (W-4 and DE 4)",
    "bank_account": "Direct deposit",
    "compensation": "Pay rate",
    "inactive": "No longer employed",
}


@dataclass
class Readiness:
    employee_id: uuid.UUID
    personal_info: bool
    withholding: bool
    bank_account: bool
    compensation: bool
    active: bool
    missing: list[str] = field(default_factory=list)  # keys of MISSING_LABELS

    @property
    def ready(self) -> bool:
        return not self.missing

    @property
    def onboarding_complete(self) -> bool:
        """The three steps the employee does themselves (ONB-1)."""
        return self.personal_info and self.withholding and self.bank_account


def current_compensation(db: Session, employee_id: uuid.UUID, as_of: date) -> Compensation | None:
    return db.scalars(
        select(Compensation)
        .where(Compensation.employee_id == employee_id, Compensation.effective_date <= as_of)
        .order_by(Compensation.effective_date.desc(), Compensation.created_at.desc())
        .limit(1)
    ).first()


def current_withholding(db: Session, employee_id: uuid.UUID, as_of: date) -> Withholding | None:
    return db.scalars(
        select(Withholding)
        .where(Withholding.employee_id == employee_id, Withholding.effective_date <= as_of)
        .order_by(Withholding.effective_date.desc(), Withholding.created_at.desc())
        .limit(1)
    ).first()


def current_deposit_account(db: Session, employee_id: uuid.UUID) -> BankAccount | None:
    return db.scalars(
        select(BankAccount)
        .where(
            BankAccount.owner_type == BankOwnerType.EMPLOYEE,
            BankAccount.employee_id == employee_id,
            BankAccount.status == BankAccountStatus.VERIFIED,
        )
        .order_by(BankAccount.created_at.desc())
        .limit(1)
    ).first()


def readiness(db: Session, employee: Employee, as_of: date) -> Readiness:
    personal = bool(
        employee.ssn_last4
        and employee.dob
        and employee.address_line1
        and employee.city
        and employee.zip
    )
    wh = current_withholding(db, employee.id, as_of) is not None
    bank = current_deposit_account(db, employee.id) is not None
    comp = current_compensation(db, employee.id, as_of) is not None
    active = employee.status == EmploymentStatus.ACTIVE
    r = Readiness(employee.id, personal, wh, bank, comp, active)
    for key, ok in (
        ("personal_info", personal),
        ("withholding", wh),
        ("bank_account", bank),
        ("compensation", comp),
        ("inactive", active),
    ):
        if not ok:
            r.missing.append(key)
    return r
