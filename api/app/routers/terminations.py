"""Termination and final paycheck (TERM-1, Journey 5). Task A-08.

- Sets end_date, separation_type, reason, status=TERMINATED. Audit EMPLOYEE_TERMINATED.
- Creates a FINAL run (state DRAFT, pay_date = due date below) with one item:
    hourly: approved-or-open minutes in unpaid periods up to end_date, at the current rate
    salary: prorate_salary(period salary, workdays worked in the period up to end_date,
            workdays in the period)  (D15), minus nothing already paid for those days
- CA due date (display only, D18):
    involuntary                -> end_date
    voluntary_with_notice      -> end_date
    voluntary_without_notice   -> end_date + 3 calendar days (72 hours)
- The membership flips to FORMER when the final run reaches PAID (hook in A-05's paid handler).
- 409 "already_terminated" if status is TERMINATED.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.adapters import get_tax_provider
from app.adapters.tax import TaxProvider
from app.auth.deps import Actor, require_staff
from app.db import get_db
from app.errors import todo
from app.schemas.employees import TerminateIn, TerminateOut

router = APIRouter(prefix="/api/employees", tags=["employees"])


@router.post("/{employee_id}/terminate", response_model=TerminateOut)
def terminate_employee(
    employee_id: uuid.UUID,
    body: TerminateIn,
    actor: Actor = Depends(require_staff),
    db: Session = Depends(get_db),
    tax: TaxProvider = Depends(get_tax_provider),
):
    todo("A-08")
