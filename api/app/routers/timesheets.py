"""Timesheets (TIME-1..3). Task B-07.

Employee side (hourly employees only; salaried -> 409 "not_hourly"):
- The "open period" = services.timesheets.open_period(db, company_id, clock.today_pacific())
  (implemented in the skeleton). Create the Timesheet lazily on GET.
- PUT entries: allowed when status OPEN or REJECTED (REJECTED -> OPEN). Dates must be inside the
  period and <= today. minutes=0 deletes the entry. LOCKED/APPROVED -> 409 "timesheet_locked".
Manager side (Admin or PM):
- approve: OPEN|REJECTED -> APPROVED. reject (note required): OPEN|APPROVED -> REJECTED.
  Audit TIMESHEET_APPROVED / TIMESHEET_REJECTED. A PM can't approve their own timesheet.
Shared services:
- lock_for_period / unlock_for_period / approved_minutes: ALREADY IMPLEMENTED in
  app/services/timesheets.py (skeleton). Reuse them; do not reimplement.
"""

import uuid

from fastapi import APIRouter, Depends
from fastapi.routing import APIRoute
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, clock
from app.auth.deps import Actor, require_employee_self, require_staff
from app.auth.scoping import get_scoped, scoped
from app.db import get_db
from app.errors import AppError, Conflict, Forbidden
from app.models import Employee, Membership, PayPeriod, PayrollRun, TimeEntry, Timesheet, User
from app.models.enums import EmploymentStatus, PayType, Role, RunState, RunType, TimesheetStatus
from app.schemas.common import PayPeriodOut
from app.schemas.timesheets import ReviewIn, TimeEntryOut, TimesheetEntriesPut, TimesheetOut
from app.services.readiness import current_compensation
from app.services.timesheets import open_period


class TimesheetRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def no_store(request):
            response = await handler(request)
            response.headers["Cache-Control"] = "no-store"
            return response

        return no_store


router = APIRouter(prefix="/api", tags=["timesheets"], route_class=TimesheetRoute)


@router.get("/me/timesheet", response_model=TimesheetOut)
def my_timesheet(actor: Actor = Depends(require_employee_self()), db: Session = Depends(get_db)):
    employee, period = _my_period(db, actor)
    return _out(db, _sheet(db, employee, period, actor), actor)


@router.put("/me/timesheet/entries", response_model=TimesheetOut)
def put_my_entries(
    body: TimesheetEntriesPut,
    actor: Actor = Depends(require_employee_self()),
    db: Session = Depends(get_db),
):
    employee, period = _my_period(db, actor)
    existing = _find_sheet(db, employee, period, actor)
    if existing:
        db.refresh(existing, with_for_update=True)
        if existing.status not in (TimesheetStatus.OPEN, TimesheetStatus.REJECTED):
            raise _locked()
    dates = set()
    for entry in body.entries:
        if (
            not period.start_date <= entry.work_date <= period.end_date
            or entry.work_date > clock.today_pacific()
        ):
            raise TimesheetValidationError(
                "Dates must be inside this pay period and no later than today.",
                code="invalid_work_date",
            )
        if entry.work_date in dates:
            raise TimesheetValidationError(
                "Include each work date only once.", code="duplicate_work_date"
            )
        dates.add(entry.work_date)
    sheet = existing or _sheet(db, employee, period, actor)
    entries = {
        entry.work_date: entry
        for entry in db.scalars(
            scoped(select(TimeEntry), TimeEntry, actor).where(TimeEntry.timesheet_id == sheet.id)
        )
    }
    for incoming in body.entries:
        entry = entries.get(incoming.work_date)
        if incoming.minutes == 0:
            if entry:
                db.delete(entry)
        elif entry:
            entry.minutes = incoming.minutes
        else:
            db.add(
                TimeEntry(
                    company_id=actor.company_id,
                    timesheet_id=sheet.id,
                    work_date=incoming.work_date,
                    minutes=incoming.minutes,
                )
            )
    if sheet.status == TimesheetStatus.REJECTED and body.entries:
        sheet.status = TimesheetStatus.OPEN
        sheet.review_note = None
        sheet.reviewed_at = None
        sheet.reviewed_by_membership_id = None
    db.flush()
    return _out(db, sheet, actor)


@router.get("/timesheets", response_model=list[TimesheetOut])
def list_timesheets(
    pay_period_id: uuid.UUID | None = None,
    actor: Actor = Depends(require_staff),
    db: Session = Depends(get_db),
):
    """Defaults to the open period. One row per active hourly employee (sheet created lazily)."""
    if pay_period_id is not None:
        period = get_scoped(db, PayPeriod, pay_period_id, actor)
    else:
        period = open_period(db, actor.company_id, clock.today_pacific())
        if period is None:
            return []
    _lock_period(db, period, actor)
    employees = db.scalars(
        scoped(select(Employee), Employee, actor)
        .where(Employee.status == EmploymentStatus.ACTIVE, Employee.hire_date <= period.end_date)
        .order_by(Employee.last_name, Employee.first_name, Employee.employee_number)
    ).all()
    result = []
    for employee in employees:
        comp = current_compensation(db, employee.id, clock.today_pacific())
        if comp and comp.pay_type == PayType.HOURLY:
            result.append(_out(db, _sheet(db, employee, period, actor), actor))
    return result


@router.post("/timesheets/{timesheet_id}/approve", response_model=TimesheetOut)
def approve_timesheet(
    timesheet_id: uuid.UUID,
    body: ReviewIn,
    actor: Actor = Depends(require_staff),
    db: Session = Depends(get_db),
):
    sheet = _review_sheet(db, timesheet_id, actor)
    if actor.role == Role.PAYROLL_MANAGER and actor.employee_id == sheet.employee_id:
        raise Forbidden("Another staff member must approve your timesheet.", code="own_timesheet")
    if sheet.status not in (TimesheetStatus.OPEN, TimesheetStatus.REJECTED):
        raise Conflict(
            "Only open or rejected timesheets can be approved.", code="illegal_timesheet_transition"
        )
    _review(db, sheet, TimesheetStatus.APPROVED, body.note, actor)
    return _out(db, sheet, actor)


@router.post("/timesheets/{timesheet_id}/reject", response_model=TimesheetOut)
def reject_timesheet(
    timesheet_id: uuid.UUID,
    body: ReviewIn,
    actor: Actor = Depends(require_staff),
    db: Session = Depends(get_db),
):
    sheet = _review_sheet(db, timesheet_id, actor)
    if sheet.status not in (TimesheetStatus.OPEN, TimesheetStatus.APPROVED):
        raise Conflict(
            "Only open or approved timesheets can be rejected.", code="illegal_timesheet_transition"
        )
    if not body.note or not body.note.strip():
        raise TimesheetValidationError(
            "Explain why these hours need correcting.", code="note_required"
        )
    _review(db, sheet, TimesheetStatus.REJECTED, body.note, actor)
    return _out(db, sheet, actor)


def _locked() -> Conflict:
    return Conflict(
        "These hours are approved or payroll has been submitted, so they cannot change.",
        code="timesheet_locked",
    )


def _run(db: Session, period: PayPeriod, actor: Actor, *, lock: bool = False) -> PayrollRun | None:
    stmt = scoped(select(PayrollRun), PayrollRun, actor).where(
        PayrollRun.pay_period_id == period.id,
        PayrollRun.run_type == RunType.REGULAR,
        PayrollRun.state != RunState.CANCELLED,
    )
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return db.scalar(stmt)


def _lock_period(db: Session, period: PayPeriod, actor: Actor) -> PayrollRun | None:
    # A-04 submits while holding the run lock, then locks approved sheets. Match that
    # lock order so approval/rejection cannot race payroll submission. The period lock
    # also serializes lazy creation and protects against schedule regeneration.
    _run(db, period, actor, lock=True)
    db.refresh(period, with_for_update=True)
    # A run may have been created while we waited for its period lock.
    return _run(db, period, actor, lock=True)


def _my_period(db: Session, actor: Actor) -> tuple[Employee, PayPeriod]:
    employee = get_scoped(db, Employee, actor.employee_id, actor)
    comp = current_compensation(db, employee.id, clock.today_pacific())
    if comp is None or comp.pay_type != PayType.HOURLY:
        raise Conflict("Only employees with a current hourly rate log hours.", code="not_hourly")
    if employee.status != EmploymentStatus.ACTIVE:
        raise Forbidden("Only active employees can log hours.")
    period = open_period(db, actor.company_id, clock.today_pacific())
    if period is None:
        raise Conflict("There is no open pay period for logging hours.", code="no_open_period")
    run = _lock_period(db, period, actor)
    if run and run.state != RunState.DRAFT:
        raise _locked()
    return employee, period


def _find_sheet(
    db: Session, employee: Employee, period: PayPeriod, actor: Actor
) -> Timesheet | None:
    return db.scalar(
        scoped(select(Timesheet), Timesheet, actor).where(
            Timesheet.employee_id == employee.id, Timesheet.pay_period_id == period.id
        )
    )


def _sheet(db: Session, employee: Employee, period: PayPeriod, actor: Actor) -> Timesheet:
    # All callers hold the period lock, so concurrent GETs create only one row.
    sheet = _find_sheet(db, employee, period, actor)
    if sheet is None:
        sheet = Timesheet(
            company_id=actor.company_id,
            employee_id=employee.id,
            pay_period_id=period.id,
            status=TimesheetStatus.OPEN,
        )
        db.add(sheet)
        db.flush()
    return sheet


def _review_sheet(db: Session, timesheet_id: uuid.UUID, actor: Actor) -> Timesheet:
    sheet = get_scoped(db, Timesheet, timesheet_id, actor)
    period = get_scoped(db, PayPeriod, sheet.pay_period_id, actor)
    run = _lock_period(db, period, actor)
    db.refresh(sheet, with_for_update=True)
    if sheet.status == TimesheetStatus.LOCKED or (run and run.state != RunState.DRAFT):
        raise _locked()
    return sheet


def _review(
    db: Session, sheet: Timesheet, status: TimesheetStatus, note: str | None, actor: Actor
) -> None:
    before = {"status": sheet.status, "review_note": sheet.review_note}
    sheet.status = status
    sheet.review_note = note.strip() if note and note.strip() else None
    sheet.reviewed_by_membership_id = actor.membership_id
    sheet.reviewed_at = clock.now()
    audit.record(
        db,
        actor=actor,
        action=audit.TIMESHEET_APPROVED
        if status == TimesheetStatus.APPROVED
        else audit.TIMESHEET_REJECTED,
        entity_type="timesheet",
        entity_id=sheet.id,
        before=before,
        after={"status": sheet.status, "review_note": sheet.review_note},
    )
    db.flush()


def _out(db: Session, sheet: Timesheet, actor: Actor) -> TimesheetOut:
    employee = get_scoped(db, Employee, sheet.employee_id, actor)
    period = get_scoped(db, PayPeriod, sheet.pay_period_id, actor)
    run = _run(db, period, actor)
    entries = db.scalars(
        scoped(select(TimeEntry), TimeEntry, actor)
        .where(TimeEntry.timesheet_id == sheet.id)
        .order_by(TimeEntry.work_date)
    ).all()
    comp = current_compensation(db, employee.id, clock.today_pacific())
    reviewer_name = None
    if sheet.reviewed_by_membership_id:
        member = get_scoped(db, Membership, sheet.reviewed_by_membership_id, actor)
        if member.employee_id:
            reviewer = get_scoped(db, Employee, member.employee_id, actor)
            reviewer_name = f"{reviewer.first_name} {reviewer.last_name}"
        else:
            reviewer_name = db.get(User, member.user_id).email
    editable = (
        actor.employee_id == employee.id
        and not actor.is_former
        and employee.status == EmploymentStatus.ACTIVE
        and sheet.status in (TimesheetStatus.OPEN, TimesheetStatus.REJECTED)
        and (run is None or run.state == RunState.DRAFT)
        and comp is not None
        and comp.pay_type == PayType.HOURLY
    )
    if editable:
        current = open_period(db, actor.company_id, clock.today_pacific())
        editable = current is not None and current.id == period.id
    return TimesheetOut(
        id=sheet.id,
        employee_id=employee.id,
        employee_name=f"{employee.first_name} {employee.last_name}",
        pay_period=PayPeriodOut(
            id=period.id,
            start_date=period.start_date,
            end_date=period.end_date,
            pay_date=period.pay_date,
            cutoff_at=period.cutoff_at,
            regular_run_id=run.id if run else None,
            regular_run_state=run.state if run else None,
        ),
        status=sheet.status,
        entries=[TimeEntryOut.model_validate(entry) for entry in entries],
        total_minutes=sum(entry.minutes for entry in entries),
        rate_cents=comp.amount_cents if comp and comp.pay_type == PayType.HOURLY else None,
        review_note=sheet.review_note,
        reviewed_by_name=reviewer_name,
        reviewed_at=sheet.reviewed_at,
        editable=editable,
    )


class TimesheetValidationError(AppError):
    status_code = 422
    code = "invalid_timesheet"
