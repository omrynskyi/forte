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
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import clock
from app.auth.deps import Actor, require_employee_self, require_staff
from app.auth.scoping import get_scoped
from app.db import get_db
from app.models import Company, Employee, PayPeriod, PayrollItem, PayrollRun, TimeEntry, Timesheet
from app.models.enums import PayType, RunState
from app.paystubs.detail import (
    VISIBLE_STATES,
    build_paystub_detail,
    build_paystub_summary,
    visible_item_or_404,
)
from app.schemas.me import HomeOut
from app.schemas.paystubs import PaystubDetail, PaystubSummary
from app.services.readiness import current_compensation, readiness
from app.services.timesheets import open_period

router = APIRouter(prefix="/api", tags=["paystubs"])


def _own_stubs(
    db: Session, actor: Actor, states: tuple[RunState, ...], limit: int | None = None
) -> list[PaystubSummary]:
    stmt = (
        select(PayrollItem, PayrollRun)
        .join(PayrollRun, PayrollRun.id == PayrollItem.run_id)
        .where(
            PayrollItem.company_id == actor.company_id,
            PayrollRun.company_id == actor.company_id,
            PayrollItem.employee_id == actor.employee_id,
            PayrollRun.state.in_(states),
        )
        .order_by(PayrollRun.pay_date.desc(), PayrollItem.created_at.desc())
    )
    if limit:
        stmt = stmt.limit(limit)
    return [build_paystub_summary(db, item, run) for item, run in db.execute(stmt).all()]


@router.get("/me/home", response_model=HomeOut)
def my_home(actor: Actor = Depends(require_employee_self()), db: Session = Depends(get_db)):
    emp = get_scoped(db, Employee, actor.employee_id, actor)  # type: ignore[arg-type]
    company = db.get(Company, actor.company_id)
    assert company is not None
    today = clock.today_pacific()
    ready = readiness(db, emp, today)
    comp = current_compensation(db, emp.id, today)
    is_hourly = comp is not None and comp.pay_type == PayType.HOURLY

    period = open_period(db, actor.company_id, today)
    next_pay_date = period.pay_date if period else None
    if next_pay_date is None:
        next_pay_date = db.scalar(
            select(func.min(PayPeriod.pay_date)).where(
                PayPeriod.company_id == actor.company_id, PayPeriod.pay_date >= today
            )
        )
    minutes = None
    if is_hourly:
        minutes = 0
        if period is not None:
            minutes = int(
                db.scalar(
                    select(func.coalesce(func.sum(TimeEntry.minutes), 0))
                    .join(Timesheet, TimeEntry.timesheet_id == Timesheet.id)
                    .where(
                        Timesheet.company_id == actor.company_id,
                        Timesheet.employee_id == emp.id,
                        Timesheet.pay_period_id == period.id,
                    )
                )
                or 0
            )
    previews = _own_stubs(db, actor, tuple(s for s in VISIBLE_STATES if s != RunState.PAID))
    return HomeOut(
        first_name=emp.first_name,
        company_name=company.legal_name,
        next_pay_date=next_pay_date,
        onboarding_complete=ready.onboarding_complete,
        missing=[k for k in ready.missing if k != "inactive"],
        is_hourly=is_hourly,
        minutes_this_period=minutes,
        upcoming=previews[-1] if previews else None,  # soonest pay date
        recent=_own_stubs(db, actor, (RunState.PAID,), limit=3),
    )


@router.get("/me/paystubs", response_model=list[PaystubSummary])
def my_paystubs(
    actor: Actor = Depends(require_employee_self(allow_former=True)),
    db: Session = Depends(get_db),
):
    """Previews first, then final stubs newest first."""
    previews = _own_stubs(db, actor, tuple(s for s in VISIBLE_STATES if s != RunState.PAID))
    return previews + _own_stubs(db, actor, (RunState.PAID,))


@router.get("/me/paystubs/{item_id}", response_model=PaystubDetail)
def my_paystub(
    item_id: uuid.UUID,
    actor: Actor = Depends(require_employee_self(allow_former=True)),
    db: Session = Depends(get_db),
):
    item, _run = visible_item_or_404(db, item_id, actor, employee_id=actor.employee_id)
    return build_paystub_detail(db, item)


@router.get("/paystubs/{item_id}", response_model=PaystubDetail)
def staff_paystub(
    item_id: uuid.UUID, actor: Actor = Depends(require_staff), db: Session = Depends(get_db)
):
    item, _run = visible_item_or_404(db, item_id, actor, employee_id=None)
    return build_paystub_detail(db, item)
