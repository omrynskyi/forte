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

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.adapters import get_payments_provider, get_tax_provider
from app.adapters.payments import PaymentsProvider
from app.adapters.tax import TaxProvider
from app.auth.deps import Actor, require_admin, require_staff
from app.auth.scoping import get_scoped, scoped
from app.db import get_db
from app.errors import Conflict, todo
from app.models import PayPeriod, PayrollRun
from app.models.enums import RunState, RunType
from app.payroll.builder import build_regular_run
from app.payroll.serializers import build_run_detail, build_run_summary
from app.payroll.state_machine import transition
from app.payroll.states import RunAction
from app.schemas.runs import RunCreate, RunDetail, RunSummary, TransitionIn
from app.services.timesheets import lock_for_period, unlock_for_period

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("", response_model=list[RunSummary])
def list_runs(
    run_type: RunType | None = None,
    state: RunState | None = None,
    actor: Actor = Depends(require_staff),
    db: Session = Depends(get_db),
):
    """Newest pay_date first. Also serves payroll history (REP-1)."""
    stmt = scoped(select(PayrollRun), PayrollRun, actor)
    if run_type is not None:
        stmt = stmt.where(PayrollRun.run_type == run_type)
    if state is not None:
        stmt = stmt.where(PayrollRun.state == state)
    runs = db.scalars(
        stmt.order_by(PayrollRun.pay_date.desc(), PayrollRun.created_at.desc(), PayrollRun.id)
    )
    return [build_run_summary(db, run, actor) for run in runs]


@router.post("", response_model=RunDetail, status_code=status.HTTP_201_CREATED)
def create_run(
    body: RunCreate,
    actor: Actor = Depends(require_staff),
    db: Session = Depends(get_db),
    tax: TaxProvider = Depends(get_tax_provider),
):
    if body.run_type == "bonus":
        todo("A-11")
    if body.pay_period_id is None:
        raise HTTPException(
            status_code=422,
            detail={"code": "pay_period_required", "message": "A regular run needs a pay period."},
        )
    period = get_scoped(db, PayPeriod, body.pay_period_id, actor)
    # Serialize creation for this period so concurrent requests get a useful 409.
    db.refresh(period, with_for_update=True)
    existing = db.scalar(
        scoped(select(PayrollRun), PayrollRun, actor).where(
            PayrollRun.pay_period_id == period.id,
            PayrollRun.run_type == RunType.REGULAR,
            PayrollRun.state != RunState.CANCELLED,
        )
    )
    if existing is not None:
        raise Conflict("A payroll run already exists for this period.", code="run_exists")
    run = PayrollRun(
        company_id=actor.company_id,
        run_type=RunType.REGULAR,
        pay_period_id=period.id,
        pay_date=period.pay_date,
        created_by_membership_id=actor.membership_id,
    )
    db.add(run)
    db.flush()
    build_regular_run(db, run, tax, clock.today_pacific(), actor=actor)
    return build_run_detail(db, run, actor)


@router.get("/{run_id}", response_model=RunDetail)
def get_run(
    run_id: uuid.UUID, actor: Actor = Depends(require_staff), db: Session = Depends(get_db)
):
    return build_run_detail(db, get_scoped(db, PayrollRun, run_id, actor), actor)


@router.post("/{run_id}/recalculate", response_model=RunDetail)
def recalculate_run(
    run_id: uuid.UUID,
    actor: Actor = Depends(require_staff),
    db: Session = Depends(get_db),
    tax: TaxProvider = Depends(get_tax_provider),
):
    run = get_scoped(db, PayrollRun, run_id, actor)
    if run.state != RunState.DRAFT:
        raise Conflict("Only draft runs can be recalculated.", code="run_not_editable")
    if run.run_type != RunType.REGULAR:
        todo(
            "A-11"
            if run.run_type == RunType.BONUS
            else "A-07"
            if run.run_type == RunType.CORRECTION
            else "A-08"
        )
    build_regular_run(db, run, tax, clock.today_pacific(), actor=actor)
    return build_run_detail(db, run, actor)


@router.post("/{run_id}/submit", response_model=RunDetail)
def submit_run(
    run_id: uuid.UUID,
    body: TransitionIn,
    actor: Actor = Depends(require_staff),
    db: Session = Depends(get_db),
):
    run = transition(db, run_id, RunAction.SUBMIT, actor=actor, note=body.note)
    if run.run_type == RunType.REGULAR:
        lock_for_period(db, run.pay_period_id, actor)
    return build_run_detail(db, run, actor)


@router.post("/{run_id}/return-to-draft", response_model=RunDetail)
def return_run_to_draft(
    run_id: uuid.UUID,
    body: TransitionIn,
    actor: Actor = Depends(require_staff),
    db: Session = Depends(get_db),
):
    run = transition(db, run_id, RunAction.RETURN_TO_DRAFT, actor=actor, note=body.note)
    if run.run_type == RunType.REGULAR:
        unlock_for_period(db, run.pay_period_id, actor)
    return build_run_detail(db, run, actor)


@router.post("/{run_id}/cancel", response_model=RunDetail)
def cancel_run(
    run_id: uuid.UUID,
    body: TransitionIn,
    actor: Actor = Depends(require_admin),
    db: Session = Depends(get_db),
):
    run = get_scoped(db, PayrollRun, run_id, actor)
    db.refresh(run, with_for_update=True)
    was_submitted = run.state == RunState.SUBMITTED
    run = transition(db, run_id, RunAction.CANCEL, actor=actor, note=body.note)
    if was_submitted and run.run_type == RunType.REGULAR:
        unlock_for_period(db, run.pay_period_id, actor)
    return build_run_detail(db, run, actor)


@router.post("/{run_id}/approve", response_model=RunDetail)
def approve_run(
    run_id: uuid.UUID,
    body: TransitionIn,
    actor: Actor = Depends(require_admin),
    db: Session = Depends(get_db),
    payments: PaymentsProvider = Depends(get_payments_provider),
):
    run = transition(db, run_id, RunAction.APPROVE, actor=actor, note=body.note)
    # A-05: start_processing(db, run, payments)
    return build_run_detail(db, run, actor)


@router.post("/{run_id}/retry", response_model=RunDetail)
def retry_run(
    run_id: uuid.UUID,
    body: TransitionIn,
    actor: Actor = Depends(require_admin),
    db: Session = Depends(get_db),
    payments: PaymentsProvider = Depends(get_payments_provider),
):
    todo("A-05")
