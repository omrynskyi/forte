"""Run builder (RUN-1, EMP-5, NFR-2). Task A-03.

    build_regular_run(db, run: PayrollRun, tax: TaxProvider, as_of: date) -> list[Blocker]

- Run must be DRAFT (the DB trigger rejects item writes otherwise). Delete existing items first.
- Employees: ACTIVE, in the run's company, hire_date <= period.end_date. For each, call
  services.readiness.readiness(); not ready -> a blocker (excluded from the run), not an error.
- Gross: salary -> money.salary_per_period(annual); hourly -> money.hourly_gross(rate,
  services.timesheets.approved_minutes(...)). Hourly employee with 0 approved minutes -> no item.
  Rate = compensation effective on period.end_date.
- Taxes: ONE batched tax.calculate([...]) call. TaxProviderError -> leave run untouched, 503.
- Item: net = gross - employee taxes; employer_cost = gross + employer taxes; bank_account_id =
  current verified deposit account.
- Totals: recompute from the items (sum) and set calculated_at. Audit RUN_RECALCULATED.
Also export `apply_tax_result(item, result)` and `recompute_totals(run, items)`: corrections (A-07)
and final paychecks (A-08) reuse them, so every run type computes money the same way.

Details settled while building it:
- The run row is locked (`SELECT ... FOR UPDATE`, the same lock transition() takes), so a rebuild
  and a submit of the same run can't interleave. A run that isn't DRAFT -> 409 "run_not_editable".
- Salaried employee hired after the period started: period salary x workdays from hire_date to
  period end / workdays in the period (money.prorate_salary, half-up). A gross of 0 -> no item.
- Readiness and withholding are read as of `as_of` (the day of the build); the pay rate is the one
  effective on period.end_date. No rate on that date -> a "compensation" blocker.
- Everything that can fail (reads, the tax call) happens BEFORE the old items are deleted, so a
  tax outage leaves the run exactly as it was: same items, totals and calculated_at, no audit row.
- `actor` (optional, keyword-only) is who asked for the build; it goes on the audit row. None means
  the system.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import audit, clock
from app.adapters.tax import TaxProvider, TaxProviderError, TaxRequest, TaxResult
from app.auth.deps import Actor
from app.errors import AppError, Conflict
from app.models import Company, Employee, PayPeriod, PayrollItem, PayrollRun
from app.models.enums import EmploymentStatus, PaySchedule, PayType, RunType
from app.money import (
    PERIODS_PER_YEAR,
    hourly_gross,
    prorate_salary,
    salary_per_period,
    workdays_between,
)
from app.payroll.states import EDITABLE_STATES
from app.services.readiness import (
    current_compensation,
    current_deposit_account,
    current_withholding,
    readiness,
)
from app.services.timesheets import approved_minutes


class TaxUnavailable(AppError):
    """The tax provider is down. The run is unchanged; the user can try again (NFR-14)."""

    status_code = 503
    code = "tax_unavailable"


@dataclass(frozen=True)
class Blocker:
    """EMP-5: an employee left out of the run, and why (keys of readiness.MISSING_LABELS).
    Same fields as schemas.runs.RunBlocker."""

    employee_id: uuid.UUID
    employee_name: str
    missing: list[str] = field(default_factory=list)


def build_regular_run(
    db: Session,
    run: PayrollRun,
    tax: TaxProvider,
    as_of: date,
    *,
    actor: Actor | None = None,
) -> list[Blocker]:
    if run.run_type != RunType.REGULAR or run.pay_period_id is None:
        raise ValueError("build_regular_run() only builds regular runs")

    # Write any pending changes, then lock the row and re-read it (same lock as transition()).
    db.flush()
    db.refresh(run, with_for_update=True)
    if run.state not in EDITABLE_STATES:
        raise Conflict(
            f"This payroll run is {run.state.value}, so its pay can't be recalculated.",
            code="run_not_editable",
            state=run.state.value,
        )

    period = db.get(PayPeriod, run.pay_period_id)
    company = db.get(Company, run.company_id)
    assert period is not None and company is not None
    periods_per_year = PERIODS_PER_YEAR[company.pay_schedule or PaySchedule.BIWEEKLY]

    employees = db.scalars(
        select(Employee)
        .where(
            Employee.company_id == run.company_id,
            Employee.status == EmploymentStatus.ACTIVE,
            Employee.hire_date <= period.end_date,
        )
        .order_by(Employee.last_name, Employee.first_name, Employee.employee_number)
    ).all()

    blockers: list[Blocker] = []
    items: list[PayrollItem] = []
    requests: list[TaxRequest] = []
    for emp in employees:
        missing = list(readiness(db, emp, as_of).missing)
        comp = current_compensation(db, emp.id, period.end_date)
        if comp is None and "compensation" not in missing:
            missing.append("compensation")  # has a rate, but only from after this period
        if missing:
            blockers.append(Blocker(emp.id, f"{emp.first_name} {emp.last_name}", missing))
            continue
        assert comp is not None

        if comp.pay_type == PayType.SALARY:
            minutes = None
            rate = salary_per_period(comp.amount_cents)
            gross = rate
            if emp.hire_date > period.start_date:
                gross = prorate_salary(
                    rate,
                    workdays_between(emp.hire_date, period.end_date),
                    workdays_between(period.start_date, period.end_date),
                )
        else:
            minutes = approved_minutes(db, emp.id, period.id)
            rate = comp.amount_cents
            gross = hourly_gross(rate, minutes)
        if gross == 0:
            continue  # no approved hours (or no workdays yet): nothing to pay, not a blocker

        wh = current_withholding(db, emp.id, as_of)
        bank = current_deposit_account(db, emp.id)
        assert wh is not None and bank is not None  # readiness() checked both
        items.append(
            PayrollItem(
                company_id=run.company_id,
                run_id=run.id,
                employee_id=emp.id,
                pay_type=comp.pay_type,
                minutes=minutes,
                rate_cents=rate,
                gross_cents=gross,
                bank_account_id=bank.id,
            )
        )
        requests.append(
            TaxRequest(
                employee_id=emp.id,
                pay_date=run.pay_date,
                gross_cents=gross,
                pay_periods_per_year=periods_per_year,
                fed_filing_status=wh.fed_filing_status,
                fed_multiple_jobs=wh.fed_multiple_jobs,
                fed_dependents_cents=wh.fed_dependents_cents,
                fed_extra_cents=wh.fed_extra_cents,
                ca_filing_status=wh.ca_filing_status,
                ca_allowances=wh.ca_allowances,
                ca_extra_cents=wh.ca_extra_cents,
            )
        )

    results = calculate_taxes(tax, requests)

    # Nothing has been written yet. From here on, replace the items in one go.
    before = _totals(run) | {"items": _item_count(db, run.id)}
    db.execute(delete(PayrollItem).where(PayrollItem.run_id == run.id))
    for item, result in zip(items, results, strict=True):
        apply_tax_result(item, result)
        db.add(item)
    recompute_totals(run, items)
    run.calculated_at = clock.now()

    audit.record(
        db,
        actor=actor,
        action=audit.RUN_RECALCULATED,
        entity_type="payroll_run",
        entity_id=run.id,
        before=before,
        after=_totals(run) | {"items": len(items), "blockers": len(blockers)},
        company_id=run.company_id,
    )
    db.flush()
    return blockers


def calculate_taxes(tax: TaxProvider, requests: list[TaxRequest]) -> list[TaxResult]:
    """One batched provider call. Results come back in request order, one per request; anything
    else (or a TaxProviderError) -> TaxUnavailable (503). No call at all for an empty batch."""
    if not requests:
        return []
    try:
        results = tax.calculate(requests)
    except TaxProviderError as e:
        raise TaxUnavailable(
            "We couldn't reach the tax service, so nothing was changed. Try again in a minute."
        ) from e
    if [r.employee_id for r in results] != [r.employee_id for r in requests]:
        raise TaxUnavailable("The tax service sent back an unexpected answer. Try again.")
    return results


def apply_tax_result(item: PayrollItem, result: TaxResult) -> None:
    """Copy one TaxResult onto an item (gross_cents must already be set) and derive net and
    employer cost. Used by every run type: regular, correction (A-07), final (A-08)."""
    if result.employee_id != item.employee_id:
        raise ValueError("tax result is for a different employee")
    item.fed_income_tax_cents = result.fed_income_tax_cents
    item.social_security_cents = result.social_security_cents
    item.medicare_cents = result.medicare_cents
    item.ca_pit_cents = result.ca_pit_cents
    item.ca_sdi_cents = result.ca_sdi_cents
    item.employer_social_security_cents = result.employer_social_security_cents
    item.employer_medicare_cents = result.employer_medicare_cents
    item.futa_cents = result.futa_cents
    item.ca_sui_cents = result.ca_sui_cents
    item.ca_ett_cents = result.ca_ett_cents
    item.tax_calculation_ref = result.calculation_ref
    deductions = item.deductions_cents or 0  # always 0 in the MVP
    item.deductions_cents = deductions
    item.net_cents = item.gross_cents - result.employee_taxes_cents - deductions
    item.employer_cost_cents = item.gross_cents + result.employer_taxes_cents


def recompute_totals(run: PayrollRun, items: list[PayrollItem]) -> None:
    """NFR-2: the run's six totals are exactly the sums of its items. Never set them any other way."""
    run.total_gross_cents = sum(i.gross_cents for i in items)
    run.total_employee_taxes_cents = sum(employee_taxes_cents(i) for i in items)
    run.total_deductions_cents = sum(i.deductions_cents or 0 for i in items)
    run.total_net_cents = sum(i.net_cents for i in items)
    run.total_employer_taxes_cents = sum(employer_taxes_cents(i) for i in items)
    run.total_company_cost_cents = sum(i.employer_cost_cents for i in items)


def employee_taxes_cents(item: PayrollItem) -> int:
    return (
        item.fed_income_tax_cents
        + item.social_security_cents
        + item.medicare_cents
        + item.ca_pit_cents
        + item.ca_sdi_cents
    )


def employer_taxes_cents(item: PayrollItem) -> int:
    return (
        item.employer_social_security_cents
        + item.employer_medicare_cents
        + item.futa_cents
        + item.ca_sui_cents
        + item.ca_ett_cents
    )


def _totals(run: PayrollRun) -> dict[str, int]:
    return {"total_gross_cents": run.total_gross_cents, "total_net_cents": run.total_net_cents}


def _item_count(db: Session, run_id: uuid.UUID) -> int:
    return len(db.scalars(select(PayrollItem.id).where(PayrollItem.run_id == run_id)).all())
