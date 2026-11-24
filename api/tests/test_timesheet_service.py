from datetime import timedelta

from app.models import PayrollRun, TimeEntry, Timesheet
from app.models.enums import RunState, RunType, TimesheetStatus
from app.services.timesheets import (
    approved_minutes,
    lock_for_period,
    open_period,
    unlock_for_period,
)
from tests import factories as f


def _sheet(db, company, emp, period, status, minutes_per_day):
    sheet = Timesheet(
        company_id=company.id, employee_id=emp.id, pay_period_id=period.id, status=status
    )
    db.add(sheet)
    db.flush()
    for i, m in enumerate(minutes_per_day):
        db.add(
            TimeEntry(
                company_id=company.id,
                timesheet_id=sheet.id,
                work_date=period.start_date + timedelta(days=i),
                minutes=m,
            )
        )
    db.flush()
    return sheet


def test_only_approved_or_locked_minutes_count(db):
    company = f.make_company(db)
    period = f.make_pay_period(db, company)
    devon = f.make_employee(db, company)
    tomas = f.make_employee(db, company, "Tomas", "Weber", amount_cents=2200)
    _sheet(db, company, devon, period, TimesheetStatus.APPROVED, [480, 480, 390])
    _sheet(db, company, tomas, period, TimesheetStatus.OPEN, [480])
    assert approved_minutes(db, devon.id, period.id) == 1350
    assert approved_minutes(db, tomas.id, period.id) == 0


def test_lock_and_unlock(db):
    company = f.make_company(db)
    period = f.make_pay_period(db, company)
    devon = f.make_employee(db, company)
    sheet = _sheet(db, company, devon, period, TimesheetStatus.APPROVED, [480])
    assert lock_for_period(db, period.id, actor=None) == 1
    db.refresh(sheet)
    assert sheet.status == TimesheetStatus.LOCKED
    assert approved_minutes(db, devon.id, period.id) == 480  # locked hours still pay
    assert unlock_for_period(db, period.id, actor=None) == 1
    db.refresh(sheet)
    assert sheet.status == TimesheetStatus.APPROVED


def test_open_period_skips_submitted_periods(db):
    from datetime import date

    company = f.make_company(db)
    first = f.make_pay_period(db, company, pay_date=date(2026, 11, 27))  # Nov 9 - Nov 22
    second = f.make_pay_period(db, company, pay_date=date(2026, 12, 11))  # Nov 23 - Dec 6
    today = date(2026, 12, 3)
    assert open_period(db, company.id, today).id == first.id
    db.add(
        PayrollRun(
            company_id=company.id,
            run_type=RunType.REGULAR,
            pay_period_id=first.id,
            pay_date=first.pay_date,
            state=RunState.PAID,
        )
    )
    db.flush()
    assert open_period(db, company.id, today).id == second.id
    assert open_period(db, company.id, date(2026, 11, 1)) is None
