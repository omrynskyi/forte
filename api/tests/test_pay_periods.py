"""B-03: biweekly date math, Pacific cutoffs, safe regeneration and lazy top-ups."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app import clock
from app.errors import Conflict
from app.models import PayPeriod, Timesheet
from app.models.enums import RunState
from app.services.pay_periods import (
    InvalidSchedule,
    add_business_days,
    calculate_cutoff,
    ensure_future_periods,
    list_periods,
    lock_company,
    set_schedule,
    validate_schedule,
)
from tests import factories as f

NOW = datetime(2026, 11, 25, 18, tzinfo=UTC)


@pytest.fixture(autouse=True)
def frozen(monkeypatch):
    monkeypatch.setattr(clock, "now", lambda: NOW)


@pytest.fixture
def context(db):
    company = f.make_company(db)
    actor = f.actor_for(db, f.make_member(db, company))
    return company, actor


@pytest.mark.parametrize(
    "start,count,expected",
    [
        (date(2026, 11, 27), 2, date(2026, 12, 1)),
        (date(2026, 11, 30), -2, date(2026, 11, 26)),
        (date(2026, 11, 28), 1, date(2026, 11, 30)),
        (date(2026, 11, 29), -1, date(2026, 11, 27)),
        (date(2026, 11, 25), 0, date(2026, 11, 25)),
    ],
)
def test_business_days(start, count, expected):
    assert add_business_days(start, count) == expected


@pytest.mark.parametrize(
    "payday,lead,expected",
    [
        (date(2026, 12, 11), 2, datetime(2026, 12, 10, 1, tzinfo=UTC)),
        # A Monday payday crosses the DST weekend; use the cutoff day's offset.
        (date(2026, 11, 2), 1, datetime(2026, 10, 31, 0, tzinfo=UTC)),
        (date(2026, 3, 9), 1, datetime(2026, 3, 7, 1, tzinfo=UTC)),
        (date(2026, 3, 13), 2, datetime(2026, 3, 12, 0, tzinfo=UTC)),
    ],
)
def test_cutoffs_and_daylight_saving(payday, lead, expected):
    assert calculate_cutoff(payday, lead) == expected


@pytest.mark.parametrize(
    "payday,lead",
    [
        (date(2026, 11, 28), 2),
        (date(2026, 11, 29), 2),
        (date(2026, 11, 26), 2),
        (date(2026, 11, 24), 1),
        (date(2026, 12, 11), 0),
        (date(2026, 12, 11), 4),
    ],
)
def test_invalid_schedule(payday, lead):
    with pytest.raises(InvalidSchedule):
        validate_schedule(payday, lead)


def test_earliest_valid_payday():
    validate_schedule(date(2026, 11, 27), 2)
    validate_schedule(date(2026, 11, 30), 3)


def test_generation_golden_case_and_idempotent_topup(db, context):
    company, actor = context
    lock_company(db, actor)
    set_schedule(db, company, date(2026, 12, 11), 2, actor)
    periods = list_periods(db, actor)
    assert len(periods) == 6
    assert periods[0].start_date == date(2026, 11, 23)
    assert periods[0].end_date == date(2026, 12, 6)
    assert periods[0].cutoff_at == datetime(2026, 12, 10, 1, tzinfo=UTC)
    assert [p.pay_date for p in periods] == [
        date(2026, 12, 11) + timedelta(days=14 * k) for k in range(6)
    ]
    ids = [p.id for p in periods]
    ensure_future_periods(db, company, actor)
    assert [p.id for p in list_periods(db, actor)] == ids


def test_lazy_topup_keeps_history_and_six_future(db, context, monkeypatch):
    company, actor = context
    lock_company(db, actor)
    set_schedule(db, company, date(2026, 12, 11), 2, actor)
    ids = {p.id for p in list_periods(db, actor)}
    monkeypatch.setattr(clock, "now", lambda: datetime(2027, 1, 10, 18, tzinfo=UTC))
    ensure_future_periods(db, company, actor)
    periods = list_periods(db, actor)
    assert len([p for p in periods if p.pay_date >= date(2027, 1, 10)]) == 6
    assert ids.issubset({p.id for p in periods})
    # Every new period remains anchored to the original biweekly sequence.
    assert all((p.pay_date - date(2026, 12, 11)).days % 14 == 0 for p in periods)


@pytest.mark.parametrize("state", [RunState.DRAFT, RunState.PAID, RunState.CANCELLED])
def test_schedule_change_preserves_periods_with_any_run(db, context, state):
    company, actor = context
    lock_company(db, actor)
    set_schedule(db, company, date(2026, 12, 11), 2, actor)
    old = db.scalars(
        select(PayPeriod).where(PayPeriod.company_id == company.id).order_by(PayPeriod.pay_date)
    ).all()
    preserved = old[0]
    run = f.make_run(db, company, period=preserved, state=state)
    snapshot = (preserved.start_date, preserved.end_date, preserved.cutoff_at)
    deleted_ids = {p.id for p in old[1:]}
    set_schedule(db, company, date(2026, 12, 18), 3, actor)
    periods = list_periods(db, actor)
    assert preserved.id in {p.id for p in periods}
    assert deleted_ids.isdisjoint({p.id for p in periods})
    assert (preserved.start_date, preserved.end_date, preserved.cutoff_at) == snapshot
    assert next(p for p in periods if p.id == preserved.id).regular_run_id == run.id
    assert len([p for p in periods if p.pay_date >= clock.today_pacific()]) == 6


def test_timesheets_protected_on_incompatible_schedule_change(db, context):
    company, actor = context
    lock_company(db, actor)
    set_schedule(db, company, date(2026, 12, 11), 2, actor)
    period = db.scalars(
        select(PayPeriod).where(PayPeriod.company_id == company.id).order_by(PayPeriod.pay_date)
    ).first()
    employee = f.make_employee(db, company)
    sheet = Timesheet(company_id=company.id, employee_id=employee.id, pay_period_id=period.id)
    db.add(sheet)
    db.flush()
    with pytest.raises(Conflict, match="timesheets"):
        set_schedule(db, company, date(2026, 12, 18), 2, actor)
    assert company.first_pay_date == date(2026, 12, 11)
    assert db.get(Timesheet, sheet.id).pay_period_id == period.id
    set_schedule(db, company, date(2026, 12, 11), 3, actor)
    assert db.get(PayPeriod, period.id).cutoff_at == calculate_cutoff(period.pay_date, 3)


def test_live_run_preferred_over_cancelled_history(db, context):
    company, actor = context
    period = f.make_pay_period(db, company)
    f.make_run(db, company, period=period, state=RunState.CANCELLED)
    live = f.make_run(db, company, period=period)
    assert list_periods(db, actor)[0].regular_run_id == live.id


def test_periods_are_scoped(db, context):
    company, actor = context
    other, other_member = f.other_company_setup(db)
    other_actor = f.actor_for(db, other_member)
    lock_company(db, actor)
    set_schedule(db, company, date(2026, 12, 11), 2, actor)
    lock_company(db, other_actor)
    set_schedule(db, other, date(2026, 12, 18), 2, other_actor)
    assert len(list_periods(db, actor)) == len(list_periods(db, other_actor)) == 6
    assert {p.id for p in list_periods(db, actor)}.isdisjoint(
        {p.id for p in list_periods(db, other_actor)}
    )
