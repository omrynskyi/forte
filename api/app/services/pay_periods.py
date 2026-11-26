"""B-03: biweekly periods and Pacific approval cutoffs (D23).

Business days are Monday-Friday; no holiday calendar is part of this MVP. A future
period has pay_date >= today's Pacific date. Keep at least six, retaining history
with runs. Company mutations and top-ups share a company row lock; existing period
rows are locked before regeneration to serialize against regular-run creation.
Never delete a timesheet to change a schedule. An incompatible schedule change on
a no-run period with timesheets returns a conflict instead. Services never commit.
"""

from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.auth.deps import Actor
from app.auth.scoping import scoped
from app.errors import AppError, Conflict, NotFound
from app.models import Company, PayPeriod, PayrollRun, Timesheet
from app.models.enums import PaySchedule, RunState, RunType
from app.schemas.common import PayPeriodOut


class InvalidSchedule(AppError):
    status_code = 422
    code = "invalid_pay_schedule"


def add_business_days(day: date, count: int) -> date:
    step = 1 if count >= 0 else -1
    for _ in range(abs(count)):
        day += timedelta(days=step)
        while day.weekday() >= 5:
            day += timedelta(days=step)
    return day


def calculate_cutoff(pay_date: date, lead_days: int) -> datetime:
    cutoff_day = add_business_days(pay_date, -lead_days)
    return datetime.combine(cutoff_day, time(17), tzinfo=clock.PACIFIC).astimezone(UTC)


def validate_schedule(first_pay_date: date, lead_days: int) -> None:
    if not 1 <= lead_days <= 3:
        raise InvalidSchedule(
            "Choose an approval deadline one to three business days before payday."
        )
    if first_pay_date.weekday() >= 5:
        raise InvalidSchedule("The first pay date must be a weekday.")
    if first_pay_date < add_business_days(clock.today_pacific(), lead_days):
        raise InvalidSchedule("The first pay date must allow enough business days for approval.")
    try:
        first_pay_date + timedelta(days=14 * 5)
    except OverflowError as exc:
        raise InvalidSchedule("Choose a pay date that allows six future periods.") from exc


def lock_company(db: Session, actor: Actor) -> Company:
    company = db.scalar(
        select(Company)
        .where(Company.id == actor.company_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if company is None:
        raise NotFound("Company not found.")
    return company


def ensure_future_periods(db: Session, company: Company, actor: Actor) -> None:
    """Caller holds lock_company; top up without changing any existing period."""
    if company.pay_schedule is None or company.first_pay_date is None:
        return
    today = clock.today_pacific()
    periods = db.scalars(scoped(select(PayPeriod), PayPeriod, actor)).all()
    future_count = sum(period.pay_date >= today for period in periods)
    dates = {period.pay_date for period in periods}
    elapsed = max(0, (today - company.first_pay_date).days)
    payday = company.first_pay_date + timedelta(days=((elapsed + 13) // 14) * 14)
    while future_count < 6:
        if payday not in dates:
            end = payday - timedelta(days=5)
            db.add(
                PayPeriod(
                    company_id=actor.company_id,
                    pay_date=payday,
                    end_date=end,
                    start_date=end - timedelta(days=13),
                    cutoff_at=calculate_cutoff(payday, company.cutoff_lead_days),
                )
            )
            dates.add(payday)
            future_count += 1
        if future_count < 6:
            payday += timedelta(days=14)
    db.flush()


def set_schedule(
    db: Session, company: Company, first_pay_date: date, lead_days: int, actor: Actor
) -> None:
    """Caller holds lock_company. Preserve runs (including cancelled) and timesheet data."""
    validate_schedule(first_pay_date, lead_days)
    periods = db.scalars(
        scoped(select(PayPeriod), PayPeriod, actor)
        .order_by(PayPeriod.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    used = set(
        db.scalars(
            scoped(select(PayrollRun.pay_period_id), PayrollRun, actor).where(
                PayrollRun.pay_period_id.is_not(None)
            )
        )
    )
    sheets = set(db.scalars(scoped(select(Timesheet.pay_period_id), Timesheet, actor)))
    for period in periods:
        if (
            period.id not in used
            and period.id in sheets
            and (period.pay_date < first_pay_date or (period.pay_date - first_pay_date).days % 14)
        ):
            raise Conflict(
                "A period has timesheets. Keep its schedule until those hours are resolved.",
                code="period_has_timesheets",
            )
    for period in periods:
        if period.id in used:
            continue
        if period.id in sheets:
            period.cutoff_at = calculate_cutoff(period.pay_date, lead_days)
        else:
            db.delete(period)
    db.flush()
    company.pay_schedule = PaySchedule.BIWEEKLY
    company.first_pay_date = first_pay_date
    company.cutoff_lead_days = lead_days
    db.flush()
    ensure_future_periods(db, company, actor)


def list_periods(db: Session, actor: Actor) -> list[PayPeriodOut]:
    periods = db.scalars(
        scoped(select(PayPeriod), PayPeriod, actor).order_by(PayPeriod.pay_date, PayPeriod.id)
    ).all()
    runs = db.scalars(
        scoped(select(PayrollRun), PayrollRun, actor)
        .where(PayrollRun.run_type == RunType.REGULAR)
        .order_by(PayrollRun.created_at, PayrollRun.id)
    ).all()
    # Prefer the live run; if all are cancelled, show the latest cancellation.
    by_period = {}
    for run in runs:
        previous = by_period.get(run.pay_period_id)
        if (
            previous is None
            or previous.state == RunState.CANCELLED
            or run.state != RunState.CANCELLED
        ):
            by_period[run.pay_period_id] = run
    return [
        PayPeriodOut(
            id=p.id,
            start_date=p.start_date,
            end_date=p.end_date,
            pay_date=p.pay_date,
            cutoff_at=p.cutoff_at,
            regular_run_id=by_period[p.id].id if p.id in by_period else None,
            regular_run_state=by_period[p.id].state if p.id in by_period else None,
        )
        for p in periods
    ]
