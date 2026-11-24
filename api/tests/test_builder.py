"""Regular run builder (A-03, RUN-1, EMP-5, NFR-2, NFR-13)."""

import time
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import DBAPIError

from app import clock
from app.adapters.mock.tax import MockTaxProvider
from app.adapters.tax import TaxProviderError, TaxRequest, TaxResult
from app.errors import Conflict
from app.models import (
    AuditLog,
    Compensation,
    PayrollItem,
    PayrollRun,
    TimeEntry,
    Timesheet,
    Withholding,
)
from app.models.enums import (
    CaFilingStatus,
    EmploymentStatus,
    FedFilingStatus,
    PayType,
    Role,
    RunState,
    RunType,
    TimesheetStatus,
)
from app.payroll.builder import (
    Blocker,
    TaxUnavailable,
    apply_tax_result,
    build_regular_run,
    employee_taxes_cents,
    employer_taxes_cents,
    recompute_totals,
)
from tests import factories as f

# Pay Fri Dec 11 2026 -> period Mon Nov 23 .. Sun Dec 6 (10 workdays), D23.
PAY_DATE = date(2026, 12, 11)
AS_OF = date(2026, 12, 7)
FIXED_NOW = datetime(2026, 12, 7, 18, 0, tzinfo=UTC)
SALARY_65K = 6_500_000  # annual cents -> 250000 per biweekly period


class SpyTax:
    """MockTaxProvider that counts calls."""

    def __init__(self) -> None:
        self.calls: list[list[TaxRequest]] = []
        self._inner = MockTaxProvider()

    def calculate(self, requests: list[TaxRequest]) -> list[TaxResult]:
        self.calls.append(list(requests))
        return self._inner.calculate(requests)


class DownTax:
    def calculate(self, requests: list[TaxRequest]) -> list[TaxResult]:
        raise TaxProviderError("timeout")


@pytest.fixture(autouse=True)
def frozen(monkeypatch):
    monkeypatch.setattr(clock, "now", lambda: FIXED_NOW)


@pytest.fixture
def company(db):
    return f.make_company(db)


@pytest.fixture
def period(db, company):
    return f.make_pay_period(db, company, PAY_DATE)


@pytest.fixture
def run(db, company, period):
    return _draft_run(db, company, period)


def _draft_run(db, company, period):
    run = PayrollRun(
        company_id=company.id,
        run_type=RunType.REGULAR,
        pay_period_id=period.id,
        pay_date=period.pay_date,
    )
    db.add(run)
    db.flush()
    return run


def _hours(db, emp, period, minutes, status=TimesheetStatus.APPROVED):
    """A timesheet with `minutes` spread over the period's days, at most 8 h a day."""
    sheet = Timesheet(
        company_id=emp.company_id, employee_id=emp.id, pay_period_id=period.id, status=status
    )
    db.add(sheet)
    db.flush()
    day = 0
    while minutes > 0:
        m = min(minutes, 480)
        db.add(
            TimeEntry(
                company_id=emp.company_id,
                timesheet_id=sheet.id,
                work_date=period.start_date + timedelta(days=day),
                minutes=m,
            )
        )
        minutes -= m
        day += 1
    db.flush()
    return sheet


def _items(db, run):
    return db.scalars(select(PayrollItem).where(PayrollItem.run_id == run.id)).all()


def _by_employee(db, run):
    return {i.employee_id: i for i in _items(db, run)}


def _assert_totals_match_items(run, items):
    assert run.total_gross_cents == sum(i.gross_cents for i in items)
    assert run.total_employee_taxes_cents == sum(employee_taxes_cents(i) for i in items)
    assert run.total_deductions_cents == sum(i.deductions_cents for i in items)
    assert run.total_net_cents == sum(i.net_cents for i in items)
    assert run.total_employer_taxes_cents == sum(employer_taxes_cents(i) for i in items)
    assert run.total_company_cost_cents == sum(i.employer_cost_cents for i in items)


# --- golden case and a mixed team ---------------------------------------------------------


def test_devon_golden_case(db, company, period, run):
    devon = f.make_employee(db, company)  # hourly $24.50, single, no extras
    _hours(db, devon, period, 80 * 60)

    blockers = build_regular_run(db, run, MockTaxProvider(), AS_OF)

    assert blockers == []
    (item,) = _items(db, run)
    assert item.pay_type == PayType.HOURLY
    assert item.minutes == 4800
    assert item.rate_cents == 2450
    assert item.gross_cents == 196_000
    assert item.fed_income_tax_cents == 23_520
    assert item.social_security_cents == 12_152
    assert item.medicare_cents == 2_842
    assert item.ca_pit_cents == 7_840
    assert item.ca_sdi_cents == 2_548
    assert item.net_cents == 147_098
    assert item.employer_cost_cents == 196_000 + 12_152 + 2_842 + 1_176 + 6_664 + 196
    assert item.tax_calculation_ref == "mock-tax-v1"
    assert item.deductions_cents == 0
    assert run.total_net_cents == 147_098
    assert run.calculated_at == FIXED_NOW


def test_mixed_team(db, company, period, run):
    ana = f.make_employee(
        db, company, "Ana", "Reyes", pay_type=PayType.SALARY, amount_cents=SALARY_65K
    )
    bo = f.make_employee(db, company, "Bo", "Chen", pay_type=PayType.SALARY, amount_cents=7_800_000)
    devon = f.make_employee(db, company)
    tomas = f.make_employee(db, company, "Tomas", "Weber", amount_cents=2200)
    new = f.make_employee(db, company, "Mia", "Novak", onboarded=False)
    _hours(db, devon, period, 80 * 60)
    _hours(db, tomas, period, 30 * 60 + 30)
    _hours(db, new, period, 8 * 60)

    blockers = build_regular_run(db, run, MockTaxProvider(), AS_OF)

    assert blockers == [
        Blocker(new.id, "Mia Novak", ["personal_info", "withholding", "bank_account"])
    ]
    items = _by_employee(db, run)
    assert set(items) == {ana.id, bo.id, devon.id, tomas.id}
    assert items[ana.id].gross_cents == 250_000
    assert items[ana.id].rate_cents == 250_000
    assert items[ana.id].minutes is None
    assert items[bo.id].gross_cents == 300_000
    assert items[devon.id].gross_cents == 196_000
    assert items[tomas.id].gross_cents == 67_100  # 30.5 h x $22.00
    for item in items.values():
        assert item.net_cents == item.gross_cents - employee_taxes_cents(item)
        assert item.employer_cost_cents == item.gross_cents + employer_taxes_cents(item)
        assert item.bank_account_id is not None
    _assert_totals_match_items(run, list(items.values()))
    assert run.total_gross_cents == 250_000 + 300_000 + 196_000 + 67_100


def test_totals_persist(db, company, period, run):
    devon = f.make_employee(db, company)
    _hours(db, devon, period, 4800)
    build_regular_run(db, run, MockTaxProvider(), AS_OF)
    db.expire_all()
    stored = db.get(PayrollRun, run.id)
    _assert_totals_match_items(stored, _items(db, stored))
    assert stored.total_gross_cents == 196_000


# --- who is in the run --------------------------------------------------------------------


def test_hourly_with_no_approved_minutes_gets_no_item(db, company, period, run):
    devon = f.make_employee(db, company)
    tomas = f.make_employee(db, company, "Tomas", "Weber")
    f.make_employee(db, company, "Lee", "Ito")  # no timesheet at all
    _hours(db, devon, period, 600, status=TimesheetStatus.OPEN)
    _hours(db, tomas, period, 600, status=TimesheetStatus.REJECTED)

    assert build_regular_run(db, run, MockTaxProvider(), AS_OF) == []
    assert _items(db, run) == []
    assert run.total_gross_cents == 0


def test_locked_timesheets_count(db, company, period, run):
    devon = f.make_employee(db, company)
    _hours(db, devon, period, 600, status=TimesheetStatus.LOCKED)
    build_regular_run(db, run, MockTaxProvider(), AS_OF)
    assert _items(db, run)[0].minutes == 600


def test_excludes_terminated_future_hires_and_other_companies(db, company, period, run):
    gone = f.make_employee(
        db, company, "Sam", "Hale", pay_type=PayType.SALARY, amount_cents=SALARY_65K
    )
    gone.status = EmploymentStatus.TERMINATED
    f.make_employee(
        db,
        company,
        "Ivy",
        "Hart",
        pay_type=PayType.SALARY,
        amount_cents=SALARY_65K,
        hire_date=period.end_date + timedelta(days=1),
    )
    other, _ = f.other_company_setup(db)
    f.make_employee(db, other, "Out", "Sider", pay_type=PayType.SALARY, amount_cents=SALARY_65K)
    db.flush()

    assert build_regular_run(db, run, MockTaxProvider(), AS_OF) == []
    assert _items(db, run) == []


def test_salaried_hired_mid_period_is_prorated(db, company, period, run):
    # Hired Tue Dec 1: works Dec 1-4 = 4 of the period's 10 workdays.
    emp = f.make_employee(
        db,
        company,
        "Ana",
        "Reyes",
        pay_type=PayType.SALARY,
        amount_cents=SALARY_65K,
        hire_date=date(2026, 12, 1),
    )
    build_regular_run(db, run, MockTaxProvider(), AS_OF)
    item = _by_employee(db, run)[emp.id]
    assert item.rate_cents == 250_000
    assert item.gross_cents == 100_000


def test_salaried_hired_on_first_day_is_not_prorated(db, company, period, run):
    emp = f.make_employee(
        db,
        company,
        "Ana",
        "Reyes",
        pay_type=PayType.SALARY,
        amount_cents=SALARY_65K,
        hire_date=period.start_date,
    )
    build_regular_run(db, run, MockTaxProvider(), AS_OF)
    assert _by_employee(db, run)[emp.id].gross_cents == 250_000


def test_salaried_hired_on_last_weekend_gets_no_item(db, company, period, run):
    # Period ends Sun Dec 6; hired Sat Dec 5 -> 0 workdays -> nothing to pay, not a blocker.
    f.make_employee(
        db,
        company,
        "Ana",
        "Reyes",
        pay_type=PayType.SALARY,
        amount_cents=SALARY_65K,
        hire_date=date(2026, 12, 5),
    )
    assert build_regular_run(db, run, MockTaxProvider(), AS_OF) == []
    assert _items(db, run) == []


def test_rate_is_the_one_effective_on_period_end(db, company, period, run):
    devon = f.make_employee(db, company)  # $24.50 since Mar 2
    db.add_all(
        [
            Compensation(  # raise inside the period: applies
                company_id=company.id,
                employee_id=devon.id,
                pay_type=PayType.HOURLY,
                amount_cents=2600,
                effective_date=period.end_date,
            ),
            Compensation(  # raise after the period: not yet
                company_id=company.id,
                employee_id=devon.id,
                pay_type=PayType.HOURLY,
                amount_cents=3000,
                effective_date=period.end_date + timedelta(days=1),
            ),
        ]
    )
    _hours(db, devon, period, 60)
    build_regular_run(db, run, MockTaxProvider(), AS_OF)
    item = _items(db, run)[0]
    assert item.rate_cents == 2600
    assert item.gross_cents == 2600


def test_rate_only_after_period_is_a_blocker(db, company, period, run):
    devon = f.make_employee(db, company)
    comp = db.scalars(select(Compensation).where(Compensation.employee_id == devon.id)).one()
    comp.effective_date = period.end_date + timedelta(days=1)  # rate starts after the period
    _hours(db, devon, period, 600)
    blockers = build_regular_run(db, run, MockTaxProvider(), AS_OF)
    assert blockers == [Blocker(devon.id, "Devon Park", ["compensation"])]
    assert _items(db, run) == []


# --- taxes --------------------------------------------------------------------------------


def test_one_batched_tax_call(db, company, period, run):
    for i in range(3):
        f.make_employee(
            db, company, f"Sal{i}", "Aried", pay_type=PayType.SALARY, amount_cents=SALARY_65K
        )
    tax = SpyTax()
    build_regular_run(db, run, tax, AS_OF)
    assert len(tax.calls) == 1
    assert len(tax.calls[0]) == 3
    req = tax.calls[0][0]
    assert req.pay_date == PAY_DATE
    assert req.pay_periods_per_year == 26


def test_no_tax_call_when_no_one_is_paid(db, company, period, run):
    tax = SpyTax()
    assert build_regular_run(db, run, tax, AS_OF) == []
    assert tax.calls == []


def test_tax_outage_leaves_the_run_untouched(db, company, period, run):
    devon = f.make_employee(db, company)
    _hours(db, devon, period, 4800)
    build_regular_run(db, run, MockTaxProvider(), AS_OF)
    (before,) = _items(db, run)
    audits = _audits(db, run)
    f.make_employee(db, company, "Ana", "Reyes", pay_type=PayType.SALARY, amount_cents=SALARY_65K)

    with pytest.raises(TaxUnavailable) as err:
        build_regular_run(db, run, DownTax(), AS_OF)

    assert err.value.status_code == 503
    assert err.value.code == "tax_unavailable"
    (after,) = _items(db, run)
    assert after.id == before.id
    assert run.total_gross_cents == 196_000
    assert run.calculated_at == FIXED_NOW
    assert len(_audits(db, run)) == len(audits)


def test_withholding_choices_reach_the_provider(db, company, period, run):
    devon = f.make_employee(db, company)
    db.add(
        Withholding(
            company_id=company.id,
            employee_id=devon.id,
            effective_date=AS_OF,
            fed_filing_status=FedFilingStatus.MARRIED_JOINTLY,
            fed_multiple_jobs=True,
            fed_dependents_cents=200_000,
            fed_extra_cents=1_000,
            ca_filing_status=CaFilingStatus.HEAD_OF_HOUSEHOLD,
            ca_allowances=2,
            ca_extra_cents=500,
        )
    )
    _hours(db, devon, period, 4800)
    tax = SpyTax()
    build_regular_run(db, run, tax, AS_OF)
    (req,) = tax.calls[0]
    assert req.fed_filing_status == FedFilingStatus.MARRIED_JOINTLY
    assert req.fed_multiple_jobs is True
    assert req.fed_dependents_cents == 200_000
    assert req.fed_extra_cents == 1_000
    assert req.ca_filing_status == CaFilingStatus.HEAD_OF_HOUSEHOLD
    assert req.ca_allowances == 2
    assert req.ca_extra_cents == 500


# --- rebuilds, state, audit ---------------------------------------------------------------


def test_rebuild_after_hours_change_replaces_items(db, company, period, run):
    devon = f.make_employee(db, company)
    sheet = _hours(db, devon, period, 4800)
    build_regular_run(db, run, MockTaxProvider(), AS_OF)
    (first,) = _items(db, run)
    first_id = first.id

    db.add(
        TimeEntry(
            company_id=company.id,
            timesheet_id=sheet.id,
            work_date=period.end_date,
            minutes=120,
        )
    )
    db.flush()
    build_regular_run(db, run, MockTaxProvider(), AS_OF)

    (second,) = _items(db, run)
    assert second.id != first_id
    assert second.minutes == 4920
    assert second.gross_cents == 200_900  # 82 h x $24.50
    assert run.total_gross_cents == 200_900
    _assert_totals_match_items(run, [second])


def test_rebuild_drops_someone_who_is_no_longer_ready(db, company, period, run):
    devon = f.make_employee(db, company)
    _hours(db, devon, period, 4800)
    build_regular_run(db, run, MockTaxProvider(), AS_OF)
    devon.ssn_last4 = None
    devon.ssn = None
    blockers = build_regular_run(db, run, MockTaxProvider(), AS_OF)
    assert [b.missing for b in blockers] == [["personal_info"]]
    assert _items(db, run) == []
    assert run.total_gross_cents == 0


def test_building_a_submitted_run_fails_clearly(db, company, period, run):
    devon = f.make_employee(db, company)
    _hours(db, devon, period, 4800)
    build_regular_run(db, run, MockTaxProvider(), AS_OF)
    run.state = RunState.SUBMITTED  # test setup only; app code uses transition()
    db.flush()

    with pytest.raises(Conflict) as err:
        build_regular_run(db, run, MockTaxProvider(), AS_OF)
    assert err.value.code == "run_not_editable"
    assert err.value.status_code == 409
    assert len(_items(db, run)) == 1


def test_db_trigger_backs_up_the_check(db, company, period, run):
    """Even if code skipped the state check, the DB refuses item writes outside DRAFT (RUN-4)."""
    devon = f.make_employee(db, company)
    _hours(db, devon, period, 4800)
    build_regular_run(db, run, MockTaxProvider(), AS_OF)
    run.state = RunState.SUBMITTED
    db.flush()
    (item,) = _items(db, run)
    item.gross_cents += 1
    item.net_cents += 1
    item.employer_cost_cents += 1
    with pytest.raises(DBAPIError, match="payroll_items are locked"):
        db.flush()
    db.rollback()


def test_rejects_non_regular_runs(db, company):
    run = PayrollRun(company_id=company.id, run_type=RunType.CORRECTION, pay_date=PAY_DATE)
    db.add(run)
    db.flush()
    with pytest.raises(ValueError):
        build_regular_run(db, run, MockTaxProvider(), AS_OF)


def test_locks_the_run_row(db, company, period, run):
    seen: list[str] = []

    def capture(conn, cursor, statement, *args):
        seen.append(statement)

    bind = db.connection()
    event.listen(bind, "before_cursor_execute", capture)
    try:
        build_regular_run(db, run, MockTaxProvider(), AS_OF)
    finally:
        event.remove(bind, "before_cursor_execute", capture)
    assert any("FROM payroll_runs" in s and "FOR UPDATE" in s for s in seen)


def _audits(db, run):
    return db.scalars(
        select(AuditLog)
        .where(AuditLog.entity_id == str(run.id), AuditLog.action == "run.recalculated")
        .order_by(AuditLog.id)
    ).all()


def test_writes_recalculated_audit(db, company, period, run):
    devon = f.make_employee(db, company)
    f.make_employee(db, company, "Mia", "Novak", onboarded=False)
    _hours(db, devon, period, 4800)
    admin = f.make_member(db, company, Role.ADMIN)
    actor = f.actor_for(db, admin)

    build_regular_run(db, run, MockTaxProvider(), AS_OF, actor=actor)

    (entry,) = _audits(db, run)
    assert entry.entity_type == "payroll_run"
    assert entry.company_id == company.id
    assert entry.actor_membership_id == admin.id
    assert entry.before == {"total_gross_cents": 0, "total_net_cents": 0, "items": 0}
    assert entry.after == {
        "total_gross_cents": 196_000,
        "total_net_cents": 147_098,
        "items": 1,
        "blockers": 1,
    }


# --- scale (NFR-13) -----------------------------------------------------------------------


def test_fifty_employees_one_call_under_two_seconds(db, company, period, run):
    for i in range(25):
        f.make_employee(
            db, company, f"Sal{i}", "Aried", pay_type=PayType.SALARY, amount_cents=SALARY_65K
        )
        hourly = f.make_employee(db, company, f"Hour{i}", "Ly")
        _hours(db, hourly, period, 4800)
    tax = SpyTax()

    start = time.perf_counter()
    blockers = build_regular_run(db, run, tax, AS_OF)
    elapsed = time.perf_counter() - start

    assert blockers == []
    assert len(tax.calls) == 1
    assert len(tax.calls[0]) == 50
    items = _items(db, run)
    assert len(items) == 50
    _assert_totals_match_items(run, items)
    assert elapsed < 2.0, f"build took {elapsed:.2f}s"


# --- the exported helpers (A-07, A-08 reuse them) -----------------------------------------


def test_apply_tax_result_and_recompute_totals_are_pure():
    emp_id = uuid.uuid4()
    result = MockTaxProvider().calculate(
        [
            TaxRequest(
                employee_id=emp_id,
                pay_date=PAY_DATE,
                gross_cents=196_000,
                pay_periods_per_year=26,
                fed_filing_status=FedFilingStatus.SINGLE,
                fed_multiple_jobs=False,
                fed_dependents_cents=0,
                fed_extra_cents=0,
                ca_filing_status=CaFilingStatus.SINGLE,
                ca_allowances=0,
                ca_extra_cents=0,
            )
        ]
    )[0]
    item = PayrollItem(employee_id=emp_id, gross_cents=196_000)
    apply_tax_result(item, result)
    assert item.net_cents == 147_098
    assert item.deductions_cents == 0

    run = PayrollRun()
    recompute_totals(run, [item, item])
    assert run.total_gross_cents == 392_000
    assert run.total_net_cents == 294_196
    assert run.total_company_cost_cents == 2 * item.employer_cost_cents

    with pytest.raises(ValueError):
        apply_tax_result(PayrollItem(employee_id=uuid.uuid4(), gross_cents=1), result)
