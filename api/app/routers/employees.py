"""Employee records and compensation (EMP-1..5, NFR-6). Task B-05.

- EMP-1: POST creates Employee (next employee_number in the company), first Compensation, an
  EMPLOYEE membership (INVITED) and sends an invite magic link.
- EMP-2: compensation is append-only; GET returns history newest first with is_current.
- EMP-3: a member can't add compensation for their own employee record -> 403 "own_compensation".
- Reveal (NFR-6): returns the full SSN or deposit account number and writes
  SENSITIVE_FIELD_REVEALED (masked values only in the audit row).
- Audit EMPLOYEE_CREATED / EMPLOYEE_UPDATED / COMPENSATION_SET.
- Termination is NOT here: see routers/terminations.py (A-08).
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.adapters import get_email_sender
from app.adapters.email import EmailSender
from app.auth.deps import Actor, require_staff
from app.db import get_db
from app.errors import todo
from app.schemas.employees import (
    CompensationIn,
    CompensationOut,
    EmployeeCreate,
    EmployeeListItem,
    EmployeeOut,
    EmployeeUpdate,
    RevealIn,
    RevealOut,
)

router = APIRouter(prefix="/api/employees", tags=["employees"])


@router.get("", response_model=list[EmployeeListItem])
def list_employees(actor: Actor = Depends(require_staff), db: Session = Depends(get_db)):
    todo("B-05")


@router.post("", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED)
def create_employee(
    body: EmployeeCreate,
    actor: Actor = Depends(require_staff),
    db: Session = Depends(get_db),
    email: EmailSender = Depends(get_email_sender),
):
    todo("B-05")


@router.get("/{employee_id}", response_model=EmployeeOut)
def get_employee(
    employee_id: uuid.UUID, actor: Actor = Depends(require_staff), db: Session = Depends(get_db)
):
    todo("B-05")


@router.patch("/{employee_id}", response_model=EmployeeOut)
def update_employee(
    employee_id: uuid.UUID,
    body: EmployeeUpdate,
    actor: Actor = Depends(require_staff),
    db: Session = Depends(get_db),
):
    todo("B-05")


@router.get("/{employee_id}/compensations", response_model=list[CompensationOut])
def list_compensations(
    employee_id: uuid.UUID, actor: Actor = Depends(require_staff), db: Session = Depends(get_db)
):
    todo("B-05")


@router.post(
    "/{employee_id}/compensations",
    response_model=CompensationOut,
    status_code=status.HTTP_201_CREATED,
)
def add_compensation(
    employee_id: uuid.UUID,
    body: CompensationIn,
    actor: Actor = Depends(require_staff),
    db: Session = Depends(get_db),
):
    todo("B-05")


@router.post("/{employee_id}/reveal", response_model=RevealOut)
def reveal_sensitive(
    employee_id: uuid.UUID,
    body: RevealIn,
    actor: Actor = Depends(require_staff),
    db: Session = Depends(get_db),
):
    todo("B-05")
