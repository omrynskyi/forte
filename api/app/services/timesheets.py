"""Timesheet queries shared by the payroll engine (A-03, A-04) and the timesheets API (B-07).
Implemented in the skeleton so the payroll track never waits on the timesheets track."""

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app import audit
from app.auth.deps import Actor
from app.models import TimeEntry, Timesheet
from app.models.enums import TimesheetStatus

PAYABLE = (TimesheetStatus.APPROVED, TimesheetStatus.LOCKED)


def approved_minutes(db: Session, employee_id: uuid.UUID, pay_period_id: uuid.UUID) -> int:
    """Minutes that count for pay: only APPROVED or LOCKED timesheets (TIME-2)."""
    total = db.scalar(
        select(func.coalesce(func.sum(TimeEntry.minutes), 0))
        .join(Timesheet, TimeEntry.timesheet_id == Timesheet.id)
        .where(
            Timesheet.employee_id == employee_id,
            Timesheet.pay_period_id == pay_period_id,
            Timesheet.status.in_(PAYABLE),
        )
    )
    return int(total or 0)


def lock_for_period(db: Session, pay_period_id: uuid.UUID, actor: Actor | None) -> int:
    """TIME-3: called when the period's regular run is SUBMITTED. APPROVED -> LOCKED."""
    n = db.execute(
        update(Timesheet)
        .where(
            Timesheet.pay_period_id == pay_period_id,
            Timesheet.status == TimesheetStatus.APPROVED,
        )
        .values(status=TimesheetStatus.LOCKED)
    ).rowcount
    if n:
        audit.record(
            db,
            actor=actor,
            action=audit.TIMESHEETS_LOCKED,
            entity_type="pay_period",
            entity_id=pay_period_id,
            after={"locked": n},
        )
    return n


def unlock_for_period(db: Session, pay_period_id: uuid.UUID, actor: Actor | None) -> int:
    """The run went back to DRAFT or was cancelled: LOCKED -> APPROVED."""
    return db.execute(
        update(Timesheet)
        .where(
            Timesheet.pay_period_id == pay_period_id,
            Timesheet.status == TimesheetStatus.LOCKED,
        )
        .values(status=TimesheetStatus.APPROVED)
    ).rowcount
