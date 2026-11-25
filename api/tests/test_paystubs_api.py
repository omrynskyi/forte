"""Paystubs API + employee home (A-06: PAY-1, PAY-2, COR-2)."""

from datetime import UTC, date, datetime

from app.models import Correction, PayrollItem, Paystub
from app.models.enums import (
    CorrectionReason,
    EmploymentStatus,
    MembershipStatus,
    PayType,
    Role,
    RunState,
    RunType,
)
from tests import factories as f

GOLDEN = (
    "You earned $1,960.00 for 80.0 hours at $24.50 an hour. $489.02 went to taxes and the "
    "disability fund. You take home $1,470.98."
)


def taxed_item(db, run, emp, *, gross=196_000, minutes=4800, pay_type=PayType.HOURLY, rate=2450):
    """An item with realistic taxes: 20000+12152+2842+11360+2548 = 48902 withheld on 196000."""
    scale = gross == 196_000
    fed, ss, med, pit, sdi = (20000, 12152, 2842, 11360, 2548) if scale else (0, 0, 0, 0, 0)
    item = PayrollItem(
        company_id=run.company_id,
        run_id=run.id,
        employee_id=emp.id,
        pay_type=pay_type,
        minutes=minutes,
        rate_cents=rate,
        gross_cents=gross,
        fed_income_tax_cents=fed,
        social_security_cents=ss,
        medicare_cents=med,
        ca_pit_cents=pit,
        ca_sdi_cents=sdi,
        net_cents=gross - (fed + ss + med + pit + sdi),
        employer_cost_cents=gross,
    )
    db.add(item)
    db.flush()
    return item


def setup(db, as_actor, state=RunState.DRAFT, **run_kw):
    company = f.make_company(db)
    emp = f.make_employee(db, company)
    member = f.make_member(db, company, Role.EMPLOYEE, employee=emp)
    run = f.make_run(db, company, **run_kw)
    item = taxed_item(db, run, emp)
    run.state = state
    db.flush()
    as_actor(member)
    return company, emp, member, run, item


def test_golden_headline_and_lines(client, db, as_actor):
    _, _, _, run, item = setup(db, as_actor, RunState.PAID)
    r = client.get(f"/api/me/paystubs/{item.id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["headline"] == GOLDEN
    assert body["is_preview"] is False
    assert body["employee_taxes_cents"] == 48902
    assert [t["code"] for t in body["taxes"]] == [
        "fed_income_tax",
        "social_security",
        "medicare",
        "ca_pit",
        "ca_sdi",
    ]
    assert all(t["explanation"] for t in body["taxes"])
    assert body["pdf_available"] is False


def test_pdf_available_follows_paystub_row(client, db, as_actor):
    company, emp, _, run, item = setup(db, as_actor, RunState.PAID)
    stub = Paystub(
        company_id=company.id,
        payroll_item_id=item.id,
        employee_id=emp.id,
        run_id=run.id,
        pay_date=run.pay_date,
        issued_at=datetime.now(UTC),
        pdf_object_key=f"companies/{company.id}/paystubs/x.pdf",
    )
    db.add(stub)
    db.flush()
    assert client.get(f"/api/me/paystubs/{item.id}").json()["pdf_available"] is True


def test_preview_visibility_follows_run_state(client, db, as_actor):
    _, _, _, run, item = setup(db, as_actor)
    # Draft: invisible
    assert client.get("/api/me/paystubs").json() == []
    assert client.get(f"/api/me/paystubs/{item.id}").status_code == 404
    for state in (RunState.SUBMITTED, RunState.APPROVED, RunState.PROCESSING, RunState.FAILED):
        run.state = state
        db.flush()
        rows = client.get("/api/me/paystubs").json()
        assert [r["id"] for r in rows] == [str(item.id)]
        assert rows[0]["is_preview"] is True
        assert client.get(f"/api/me/paystubs/{item.id}").json()["is_preview"] is True
    run.state = RunState.DRAFT  # returned to draft
    db.flush()
    assert client.get("/api/me/paystubs").json() == []
    run.state = RunState.CANCELLED
    db.flush()
    assert client.get("/api/me/paystubs").json() == []
    assert client.get(f"/api/me/paystubs/{item.id}").status_code == 404


def test_list_orders_previews_first_then_final_newest_first(client, db, as_actor):
    company, emp, _, run, item = setup(db, as_actor, RunState.PAID)
    older = f.make_run(db, company, state=RunState.DRAFT)
    older.pay_date = date(2026, 1, 1)
    old_item = taxed_item(db, older, emp)
    older.state = RunState.PAID
    prev = f.make_run(db, company, state=RunState.DRAFT)
    prev_item = taxed_item(db, prev, emp)
    prev.state = RunState.SUBMITTED
    db.flush()
    ids = [r["id"] for r in client.get("/api/me/paystubs").json()]
    assert ids == [str(prev_item.id), str(item.id), str(old_item.id)]


def test_isolation_between_employees_and_companies(client, db, as_actor):
    company, emp, member, run, item = setup(db, as_actor, RunState.PAID)
    # another employee in the same company
    emp2 = f.make_employee(db, company, "Sam", "Lee")
    member2 = f.make_member(db, company, Role.EMPLOYEE, employee=emp2)
    as_actor(member2)
    assert client.get(f"/api/me/paystubs/{item.id}").status_code == 404
    assert client.get("/api/me/paystubs").json() == []
    # another company's staff
    _, other_admin = f.other_company_setup(db)
    as_actor(other_admin)
    assert client.get(f"/api/paystubs/{item.id}").status_code == 404


def test_former_employee_reads_own(client, db, as_actor):
    _, emp, member, run, item = setup(db, as_actor, RunState.PAID, run_type=RunType.FINAL)
    emp.status = EmploymentStatus.TERMINATED
    member.status = MembershipStatus.FORMER
    db.flush()
    as_actor(member)
    assert len(client.get("/api/me/paystubs").json()) == 1
    r = client.get(f"/api/me/paystubs/{item.id}")
    assert r.status_code == 200
    assert r.json()["headline"].startswith("This is your final paycheck.")


def test_staff_reads_any_employee_in_company(client, db, as_actor):
    company, emp, _, run, item = setup(db, as_actor, RunState.PAID)
    admin = f.make_member(db, company, Role.ADMIN)
    as_actor(admin)
    r = client.get(f"/api/paystubs/{item.id}")
    assert r.status_code == 200
    assert r.json()["headline"] == GOLDEN
    assert r.json()["employee_name"] == "Devon Park"


def test_salary_headline(client, db, as_actor):
    company = f.make_company(db)
    emp = f.make_employee(db, company, pay_type=PayType.SALARY, amount_cents=6_500_000)
    member = f.make_member(db, company, Role.EMPLOYEE, employee=emp)
    run = f.make_run(db, company)
    item = taxed_item(db, run, emp, pay_type=PayType.SALARY, minutes=None, rate=250_000)
    run.state = RunState.PAID
    db.flush()
    as_actor(member)
    h = client.get(f"/api/me/paystubs/{item.id}").json()["headline"]
    assert h.startswith("You earned $1,960.00 in salary for this pay period.")


def test_correction_links_and_headline(client, db, as_actor):
    company, emp, member, run, item = setup(db, as_actor, RunState.PAID)
    run.pay_date = date(2026, 10, 30)
    corr_run = f.make_run(db, company, run_type=RunType.CORRECTION, state=RunState.DRAFT)
    corr_item = taxed_item(db, corr_run, emp, gross=15_925, minutes=390)
    corr_run.state = RunState.SUBMITTED
    corr = Correction(
        company_id=company.id,
        employee_id=emp.id,
        original_item_id=item.id,
        correction_run_id=corr_run.id,
        reason=list(CorrectionReason)[0],
        missed_minutes=390,
    )
    db.add(corr)
    db.flush()

    orig = client.get(f"/api/me/paystubs/{item.id}").json()
    assert len(orig["corrections"]) == 1
    brief = orig["corrections"][0]
    assert brief["status"] == "in_review"
    assert brief["correction_item_id"] == str(corr_item.id)
    assert brief["gross_cents"] == 15_925
    assert orig["corrects_item_id"] is None

    detail = client.get(f"/api/me/paystubs/{corr_item.id}").json()
    assert detail["corrects_item_id"] == str(item.id)
    assert detail["headline"].startswith(
        "You earned $159.25 for 6.5 hours you were owed on your Oct 30 paycheck."
    )

    corr_run.state = RunState.PAID
    db.flush()
    assert client.get(f"/api/me/paystubs/{item.id}").json()["corrections"][0]["status"] == "paid"


def test_home(client, db, as_actor):
    company, emp, member, run, item = setup(db, as_actor, RunState.PAID)
    prev = f.make_run(db, company, state=RunState.DRAFT)
    prev_item = taxed_item(db, prev, emp)
    prev.state = RunState.SUBMITTED
    db.flush()
    r = client.get("/api/me/home")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["first_name"] == "Devon"
    assert body["company_name"] == "Larkspur Bakery, Inc."
    assert body["is_hourly"] is True
    assert body["onboarding_complete"] is True
    assert body["missing"] == []
    assert body["upcoming"]["id"] == str(prev_item.id)
    assert body["upcoming"]["is_preview"] is True
    assert [s["id"] for s in body["recent"]] == [str(item.id)]


def test_home_recent_is_capped_at_three(client, db, as_actor):
    company, emp, member, run, item = setup(db, as_actor, RunState.PAID)
    for _ in range(4):
        r = f.make_run(db, company, state=RunState.DRAFT)
        taxed_item(db, r, emp)
        r.state = RunState.PAID
    db.flush()
    body = client.get("/api/me/home").json()
    assert len(body["recent"]) == 3
    assert body["upcoming"] is None
