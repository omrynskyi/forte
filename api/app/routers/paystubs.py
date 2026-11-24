"""Paystubs + employee home (PAY-1, PAY-2, COR-2, TERM-2). Task A-06.

Visibility for an employee (actor.employee_id), including FORMER employees (read-only):
- final:   items whose run is PAID
- preview: items whose run is SUBMITTED / APPROVED / PROCESSING / FAILED (is_preview=True)
- never:   DRAFT or CANCELLED runs (a cancelled or returned run's preview disappears)
Plain language (PAY-1): headline + one explanation per line from app/paystubs/templates.py, which
this task creates. Copy is written by us, stored as templates, never generated on the fly.
Staff view GET /api/paystubs/{id} returns the same PaystubDetail for any employee in the company.
PDF download is NOT here: see routers/paystub_pdfs.py (A-13).
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.deps import Actor, require_employee_self, require_staff
from app.db import get_db
from app.errors import todo
from app.schemas.me import HomeOut
from app.schemas.paystubs import PaystubDetail, PaystubSummary

router = APIRouter(prefix="/api", tags=["paystubs"])


@router.get("/me/home", response_model=HomeOut)
def my_home(actor: Actor = Depends(require_employee_self()), db: Session = Depends(get_db)):
    todo("A-06")


@router.get("/me/paystubs", response_model=list[PaystubSummary])
def my_paystubs(
    actor: Actor = Depends(require_employee_self(allow_former=True)),
    db: Session = Depends(get_db),
):
    """Previews first, then final stubs newest first."""
    todo("A-06")


@router.get("/me/paystubs/{item_id}", response_model=PaystubDetail)
def my_paystub(
    item_id: uuid.UUID,
    actor: Actor = Depends(require_employee_self(allow_former=True)),
    db: Session = Depends(get_db),
):
    todo("A-06")


@router.get("/paystubs/{item_id}", response_model=PaystubDetail)
def staff_paystub(
    item_id: uuid.UUID, actor: Actor = Depends(require_staff), db: Session = Depends(get_db)
):
    todo("A-06")
