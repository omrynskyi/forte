"""Payroll runs API (RUN-1..6). Task A-04. Thin layer over app/payroll/builder.py (A-03) and
app/payroll/state_machine.py (A-02).

- POST: regular run for a pay period (409 "run_exists" if a live one exists). Builds items right
  away (state DRAFT). bonus -> A-11 (P1), return 501 until then.
- POST /{id}/recalculate: DRAFT only; rebuild items from current data.
- POST /{id}/submit: transition SUBMIT, then timesheets.lock_for_period (regular runs).
- POST /{id}/return-to-draft: transition, then unlock_for_period.
- POST /{id}/cancel: transition (Admin); unlock_for_period if it was SUBMITTED.
- POST /{id}/approve: transition APPROVE, then hand off to payments (A-05's
  `payroll.payouts.start_processing(db, run, payments)`) in the same request.
- POST /{id}/retry: FAILED -> PROCESSING with the SAME idempotency key (A-05).
- Every response is a RunDetail with allowed_actions filtered for the caller's role.
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.adapters import get_payments_provider, get_tax_provider
from app.adapters.payments import PaymentsProvider
from app.adapters.tax import TaxProvider
from app.auth.deps import Actor, require_admin, require_staff
from app.db import get_db
from app.errors import todo
from app.models.enums import RunState, RunType
from app.schemas.runs import RunCreate, RunDetail, RunSummary, TransitionIn

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("", response_model=list[RunSummary])
def list_runs(
    run_type: RunType | None = None,
    state: RunState | None = None,
    actor: Actor = Depends(require_staff),
    db: Session = Depends(get_db),
):
    """Newest pay_date first. Also serves payroll history (REP-1)."""
    todo("A-04")


@router.post("", response_model=RunDetail, status_code=status.HTTP_201_CREATED)
def create_run(
    body: RunCreate,
    actor: Actor = Depends(require_staff),
    db: Session = Depends(get_db),
    tax: TaxProvider = Depends(get_tax_provider),
):
    todo("A-04")


@router.get("/{run_id}", response_model=RunDetail)
def get_run(
    run_id: uuid.UUID, actor: Actor = Depends(require_staff), db: Session = Depends(get_db)
):
    todo("A-04")


@router.post("/{run_id}/recalculate", response_model=RunDetail)
def recalculate_run(
    run_id: uuid.UUID,
    actor: Actor = Depends(require_staff),
    db: Session = Depends(get_db),
    tax: TaxProvider = Depends(get_tax_provider),
):
    todo("A-04")


@router.post("/{run_id}/submit", response_model=RunDetail)
def submit_run(
    run_id: uuid.UUID,
    body: TransitionIn,
    actor: Actor = Depends(require_staff),
    db: Session = Depends(get_db),
):
    todo("A-04")


@router.post("/{run_id}/return-to-draft", response_model=RunDetail)
def return_run_to_draft(
    run_id: uuid.UUID,
    body: TransitionIn,
    actor: Actor = Depends(require_staff),
    db: Session = Depends(get_db),
):
    todo("A-04")


@router.post("/{run_id}/cancel", response_model=RunDetail)
def cancel_run(
    run_id: uuid.UUID,
    body: TransitionIn,
    actor: Actor = Depends(require_admin),
    db: Session = Depends(get_db),
):
    todo("A-04")


@router.post("/{run_id}/approve", response_model=RunDetail)
def approve_run(
    run_id: uuid.UUID,
    body: TransitionIn,
    actor: Actor = Depends(require_admin),
    db: Session = Depends(get_db),
    payments: PaymentsProvider = Depends(get_payments_provider),
):
    todo("A-04")


@router.post("/{run_id}/retry", response_model=RunDetail)
def retry_run(
    run_id: uuid.UUID,
    body: TransitionIn,
    actor: Actor = Depends(require_admin),
    db: Session = Depends(get_db),
    payments: PaymentsProvider = Depends(get_payments_provider),
):
    todo("A-05")
