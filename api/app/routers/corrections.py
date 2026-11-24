"""Corrections (COR-1, COR-2, Journey 4). Task A-07. Reason "missed_hours" only (D11); pays the
difference only, never recovers (D19).

- The original item must be on a PAID run, be hourly, and belong to the caller's company.
- gross = hourly_gross(original.rate_cents, missed_minutes); taxes from TaxProvider using the
  employee's CURRENT withholding; net = gross - taxes.
- POST creates a CORRECTION run (DRAFT, pay_date = next business day, original_run_id = original
  run) with one item (memo "Correction: 6.5 missed hours on <pay date>") and a Correction row.
  Audit CORRECTION_OPENED + RUN_CREATED. The run then goes through the normal lifecycle.
- Status is derived from the run (app/payroll/states.py::correction_status).
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.adapters import get_tax_provider
from app.adapters.tax import TaxProvider
from app.auth.deps import Actor, require_staff
from app.db import get_db
from app.errors import todo
from app.schemas.corrections import CorrectionIn, CorrectionOut, CorrectionPreview

router = APIRouter(prefix="/api/corrections", tags=["corrections"])


@router.post("/preview", response_model=CorrectionPreview)
def preview_correction(
    body: CorrectionIn,
    actor: Actor = Depends(require_staff),
    db: Session = Depends(get_db),
    tax: TaxProvider = Depends(get_tax_provider),
):
    todo("A-07")


@router.post("", response_model=CorrectionOut, status_code=status.HTTP_201_CREATED)
def create_correction(
    body: CorrectionIn,
    actor: Actor = Depends(require_staff),
    db: Session = Depends(get_db),
    tax: TaxProvider = Depends(get_tax_provider),
):
    todo("A-07")


@router.get("", response_model=list[CorrectionOut])
def list_corrections(
    employee_id: uuid.UUID | None = None,
    actor: Actor = Depends(require_staff),
    db: Session = Depends(get_db),
):
    todo("A-07")
