"""Database-level guarantees from migration 0001. If one of these fails, a rule in the PRD is no
longer enforced by the database."""

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.models import AuditLog, PayrollItem, PayrollRun, Paystub
from app.models.enums import PayType, RunState, RunType
from tests import factories as f


def _run_with_item(db, state=RunState.DRAFT):
    company = f.make_company(db)
    emp = f.make_employee(db, company)
    period = f.make_pay_period(db, company)
    run = PayrollRun(
        company_id=company.id,
        run_type=RunType.REGULAR,
        pay_period_id=period.id,
        pay_date=period.pay_date,
    )
    db.add(run)
    db.flush()
    item = PayrollItem(
        company_id=company.id,
        run_id=run.id,
        employee_id=emp.id,
        pay_type=PayType.HOURLY,
        minutes=4800,
        rate_cents=2450,
        gross_cents=196000,
        fed_income_tax_cents=23520,
        social_security_cents=12152,
        medicare_cents=2842,
        ca_pit_cents=7840,
        ca_sdi_cents=2548,
        net_cents=147098,
        employer_social_security_cents=12152,
        employer_medicare_cents=2842,
        futa_cents=1176,
        ca_sui_cents=6664,
        ca_ett_cents=196,
        employer_cost_cents=219030,
    )
    db.add(item)
    db.flush()
    if state != RunState.DRAFT:
        run.state = state
        db.flush()
    return company, emp, run, item


def test_audit_log_is_insert_only(db):
    db.add(AuditLog(action="test.done", entity_type="x", entity_id="1"))
    db.flush()
    with pytest.raises(DBAPIError, match="insert-only"):
        db.execute(text("UPDATE audit_log SET action = 'tampered'"))
    db.rollback()
    db.add(AuditLog(action="test.done", entity_type="x", entity_id="2"))
    db.flush()
    with pytest.raises(DBAPIError, match="insert-only"):
        db.execute(text("DELETE FROM audit_log"))
    db.rollback()


def test_items_locked_after_submit(db):
    _, _, _, item = _run_with_item(db, state=RunState.SUBMITTED)
    item.gross_cents = 1
    item.net_cents = 1 - 48902
    with pytest.raises(DBAPIError, match="locked"):
        db.flush()
    db.rollback()


def test_net_must_equal_gross_minus_withholding(db):
    company, emp, run, item = _run_with_item(db)
    item.net_cents += 1
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_paystub_pdf_is_set_once(db):
    company, emp, run, item = _run_with_item(db)
    run.state = RunState.PAID
    db.flush()
    stub = Paystub(
        company_id=company.id,
        payroll_item_id=item.id,
        employee_id=emp.id,
        run_id=run.id,
        pay_date=date(2026, 12, 11),
        issued_at=datetime.now(UTC),
    )
    db.add(stub)
    db.flush()
    stub.pdf_object_key = f"companies/{company.id}/paystubs/{stub.id}.pdf"  # first set: allowed
    stub.pdf_sha256 = "a" * 64
    db.flush()
    stub.pdf_object_key = f"companies/{company.id}/paystubs/{uuid.uuid4()}.pdf"
    with pytest.raises(DBAPIError, match="immutable"):
        db.flush()
    db.rollback()


def test_one_live_regular_run_per_period(db):
    company, _, run, _ = _run_with_item(db)
    db.add(
        PayrollRun(
            company_id=company.id,
            run_type=RunType.REGULAR,
            pay_period_id=run.pay_period_id,
            pay_date=run.pay_date,
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()
