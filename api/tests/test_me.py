"""B-06: onboarding, append-only withholding, encrypted secrets and self-service boundaries."""

import secrets
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app import audit, clock
from app.adapters import get_bank_verifier
from app.adapters.bank import BankVerification
from app.auth.tokens import hash_token
from app.config import get_settings
from app.db import get_db
from app.main import app
from app.models import AuditLog, AuthSession, BankAccount, Compensation, Employee, Withholding
from app.models.enums import BankAccountStatus, MembershipStatus, Role
from app.security.crypto import decrypt
from app.services.readiness import current_withholding, readiness
from tests import factories as f

NOW = datetime(2026, 11, 25, 18, tzinfo=UTC)
PERSONAL = {
    "first_name": "Devon",
    "last_name": "Park",
    "dob": "1995-06-01",
    "ssn": "123-45-4821",
    "address": {"line1": "411 Willow Glen Way", "city": "San Jose", "state": "CA", "zip": "95125"},
}
WITHHOLDING = {
    "fed_filing_status": "single",
    "fed_multiple_jobs": True,
    "fed_dependents_cents": 200000,
    "fed_extra_cents": 1500,
    "ca_filing_status": "single",
    "ca_allowances": 2,
    "ca_extra_cents": 500,
}
BANK = {"routing_number": "110000000", "account_number": "000123453347", "account_type": "checking"}


@pytest.fixture(autouse=True)
def frozen(monkeypatch):
    monkeypatch.setattr(clock, "now", lambda: NOW)


@pytest.fixture
def employee_context(db, client):
    company = f.make_company(db)
    employee = f.make_employee(db, company, onboarded=False)
    member = f.make_member(db, company, Role.EMPLOYEE, employee=employee)
    cookie = secrets.token_urlsafe(32)
    db.add(
        AuthSession(
            user_id=member.user_id,
            token_hash=hash_token(cookie),
            expires_at=NOW + timedelta(hours=12),
        )
    )
    db.flush()
    client.cookies.set(get_settings().session_cookie_name, cookie)
    return company, employee, member


def assert_private(response):
    for secret in (PERSONAL["ssn"], PERSONAL["ssn"].replace("-", ""), BANK["account_number"]):
        assert secret not in response.text


def test_three_steps_make_employee_ready(client, db, employee_context):
    company, employee, member = employee_context
    profile = client.get("/api/me/profile")
    assert profile.status_code == 200
    assert profile.headers["cache-control"] == "no-store"
    assert profile.json()["address"] is None
    assert profile.json()["withholding"] is None
    assert profile.json()["deposit_account"] is None
    assert not readiness(db, employee, clock.today_pacific()).ready
    personal = client.put("/api/me/personal", json=PERSONAL)
    assert personal.status_code == 200, personal.text
    assert personal.json()["ssn_last4"] == "4821"
    assert personal.json()["dob"] == "1995-06-01"
    assert personal.json()["address"] == {**PERSONAL["address"], "line2": None}
    withholding = client.put("/api/me/withholding", json=WITHHOLDING)
    assert withholding.status_code == 200, withholding.text
    assert withholding.json()["effective_date"] == "2026-11-25"
    for key, value in WITHHOLDING.items():
        assert withholding.json()[key] == value
    assert not readiness(db, employee, clock.today_pacific()).ready
    bank = client.put("/api/me/bank-account", json=BANK)
    assert bank.status_code == 200, bank.text
    assert bank.json()["account_last4"] == "3347"
    assert bank.json()["status"] == "verified"
    db.refresh(employee)
    ready = readiness(db, employee, clock.today_pacific())
    assert ready.ready and ready.onboarding_complete
    profile = client.get("/api/me/profile")
    assert profile.json()["employee_id"] == str(employee.id)
    assert profile.json()["company_name"] == company.legal_name
    assert profile.json()["job_title"] == "Counter lead"
    assert profile.json()["is_former"] is False
    assert profile.json()["withholding"] == withholding.json()
    assert profile.json()["deposit_account"] == bank.json()
    for response in (personal, withholding, bank, profile):
        assert_private(response)
    raw_ssn = db.execute(
        text("SELECT ssn FROM employees WHERE id = :id"), {"id": employee.id}
    ).scalar_one()
    assert decrypt(raw_ssn) == "123454821"
    assert raw_ssn != "123454821"
    raw_bank = db.execute(
        text("SELECT account_number FROM bank_accounts WHERE employee_id = :id"),
        {"id": employee.id},
    ).scalar_one()
    assert decrypt(raw_bank) == BANK["account_number"]
    audits = db.scalars(select(AuditLog).where(AuditLog.company_id == company.id)).all()
    assert {entry.action for entry in audits} == {
        audit.EMPLOYEE_PERSONAL_INFO_SET,
        audit.WITHHOLDING_SET,
        audit.BANK_ACCOUNT_SET,
    }
    for entry in audits:
        assert entry.actor_membership_id == member.id
        assert entry.actor_user_id == member.user_id
        for secret in (PERSONAL["ssn"], "123454821", BANK["account_number"]):
            assert secret not in str(entry.before)
            assert secret not in str(entry.after)


def test_withholding_versions_keep_history_and_latest_wins_same_clock_tick(
    client, db, employee_context
):
    _, employee, member = employee_context
    first = client.put("/api/me/withholding", json=WITHHOLDING)
    second = client.put("/api/me/withholding", json={**WITHHOLDING, "fed_extra_cents": 2500})
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] != second.json()["id"]
    versions = db.scalars(
        select(Withholding)
        .where(Withholding.employee_id == employee.id)
        .order_by(Withholding.created_at)
    ).all()
    assert len(versions) == 2
    assert [v.fed_extra_cents for v in versions] == [1500, 2500]
    assert all(v.created_by_membership_id == member.id for v in versions)
    assert current_withholding(db, employee.id, clock.today_pacific()).id == versions[-1].id
    assert client.get("/api/me/profile").json()["withholding"] == second.json()


def test_future_withholding_does_not_override_current_profile(client, db, employee_context):
    company, employee, _ = employee_context
    current = client.put("/api/me/withholding", json=WITHHOLDING).json()
    db.add(
        Withholding(
            company_id=company.id,
            employee_id=employee.id,
            effective_date=date(2027, 1, 1),
            **{**WITHHOLDING, "fed_extra_cents": 9999},
        )
    )
    db.flush()
    assert client.get("/api/me/profile").json()["withholding"] == current


def test_bank_replaces_only_current_employee_accounts(client, db, employee_context):
    company, employee, _ = employee_context
    previous = f.make_bank_account(db, company, employee=employee)
    colleague = f.make_employee(db, company, "Bo", "Chen")
    colleague_bank = db.scalar(select(BankAccount).where(BankAccount.employee_id == colleague.id))
    funding = f.make_bank_account(db, company)
    other_company, _ = f.other_company_setup(db)
    other_employee = f.make_employee(db, other_company)
    foreign_bank = db.scalar(
        select(BankAccount).where(BankAccount.employee_id == other_employee.id)
    )
    response = client.put("/api/me/bank-account", json={**BANK, "account_number": "000123459876"})
    assert response.status_code == 200
    assert response.json()["account_last4"] == "9876"
    db.refresh(previous)
    assert previous.status == BankAccountStatus.REPLACED
    for untouched in (colleague_bank, funding, foreign_bank):
        db.refresh(untouched)
        assert untouched.status == BankAccountStatus.VERIFIED
    assert client.get("/api/me/profile").json()["deposit_account"]["id"] == response.json()["id"]
    entry = db.scalars(select(AuditLog).where(AuditLog.action == audit.BANK_ACCOUNT_SET)).one()
    assert entry.before == {"account_last4": "3347"}
    assert entry.after == {"account_last4": "9876"}


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"routing_number": "123456789"}, "That routing number isn't valid."),
        ({"account_number": "12340000"}, "The bank couldn't confirm this account."),
    ],
)
def test_bank_failure_keeps_previous_verified_account(
    client, db, employee_context, changes, reason
):
    company, employee, _ = employee_context
    previous = f.make_bank_account(db, company, employee=employee)
    response = client.put("/api/me/bank-account", json={**BANK, **changes})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "bank_verification_failed"
    assert response.json()["detail"]["reason"] == reason
    assert_private(response)
    db.refresh(previous)
    assert previous.status == BankAccountStatus.VERIFIED
    assert db.scalar(select(func.count()).select_from(BankAccount)) == 1
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 0


def test_injected_bank_verifier_is_used(client, db, employee_context):
    calls = []

    class Verifier:
        def verify(self, routing_number, account_number):
            calls.append((routing_number, account_number))
            return BankVerification("verified", "self-service-bank-ref")

    app.dependency_overrides[get_bank_verifier] = Verifier
    response = client.put("/api/me/bank-account", json=BANK)
    assert response.status_code == 200
    assert calls == [(BANK["routing_number"], BANK["account_number"])]
    assert db.scalar(select(BankAccount.provider_ref)) == "self-service-bank-ref"


def test_former_can_read_profile_but_cannot_write(client, db, employee_context):
    _, employee, member = employee_context
    member.status = MembershipStatus.FORMER
    employee.end_date = date(2026, 11, 20)
    db.flush()
    response = client.get("/api/me/profile")
    assert response.status_code == 200
    assert response.json()["is_former"] is True
    assert response.json()["end_date"] == "2026-11-20"
    for endpoint, body in (
        ("personal", PERSONAL),
        ("withholding", WITHHOLDING),
        ("bank-account", BANK),
    ):
        assert client.put(f"/api/me/{endpoint}", json=body).status_code == 403
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 0


def test_employee_cannot_change_pay_job_email_or_target_another_employee(
    client, db, employee_context
):
    company, employee, _ = employee_context
    colleague = f.make_employee(db, company, "Bo", "Chen")
    before_email, before_job = employee.email, employee.job_title
    compensation = db.scalars(
        select(Compensation).where(Compensation.employee_id == employee.id)
    ).one()
    before_pay = compensation.amount_cents
    response = client.put(
        "/api/me/personal",
        json={
            **PERSONAL,
            "first_name": "Devon Updated",
            "employee_id": str(colleague.id),
            "job_title": "CEO",
            "email": "changed@larkspur.example",
            "amount_cents": 99999999,
        },
    )
    assert response.status_code == 200
    db.refresh(employee)
    db.refresh(colleague)
    db.refresh(compensation)
    assert employee.first_name == "Devon Updated"
    assert colleague.first_name == "Bo"
    assert employee.job_title == before_job
    assert employee.email == before_email
    assert compensation.amount_cents == before_pay


@pytest.mark.parametrize(
    "endpoint,body",
    [
        ("profile", None),
        ("personal", PERSONAL),
        ("withholding", WITHHOLDING),
        ("bank-account", BANK),
    ],
)
def test_cross_tenant_employee_reference_returns_404(
    client, db, employee_context, as_actor, endpoint, body
):
    _, _, member = employee_context
    other, _ = f.other_company_setup(db)
    foreign = f.make_employee(db, other)
    actor = replace(f.actor_for(db, member), employee_id=foreign.id)
    as_actor(actor)
    response = (
        client.get("/api/me/profile")
        if body is None
        else client.put(f"/api/me/{endpoint}", json=body)
    )
    assert response.status_code == 404
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 0


@pytest.mark.parametrize("role", [Role.ADMIN, Role.PAYROLL_MANAGER])
def test_staff_not_on_payroll_cannot_use_employee_endpoints(client, db, as_actor, role):
    company = f.make_company(db)
    as_actor(f.make_member(db, company, role))
    assert client.get("/api/me/profile").status_code == 403
    for endpoint, body in (
        ("personal", PERSONAL),
        ("withholding", WITHHOLDING),
        ("bank-account", BANK),
    ):
        assert client.put(f"/api/me/{endpoint}", json=body).status_code == 403


@pytest.mark.parametrize(
    "endpoint,body",
    [
        ("profile", None),
        ("personal", PERSONAL),
        ("withholding", WITHHOLDING),
        ("bank-account", BANK),
    ],
)
def test_missing_session_returns_401(client, endpoint, body):
    response = (
        client.get("/api/me/profile")
        if body is None
        else client.put(f"/api/me/{endpoint}", json=body)
    )
    assert response.status_code == 401


@pytest.mark.parametrize(
    "changes",
    [
        {"ssn": "123-45-482"},
        {"ssn": "１２３４５４８２１"},
        {"dob": "2099-01-01"},
        {"dob": "invalid"},
        {"address": {**PERSONAL["address"], "state": "NY"}},
    ],
)
def test_invalid_personal_data_is_private_and_does_not_write(client, db, employee_context, changes):
    response = client.put("/api/me/personal", json={**PERSONAL, **changes})
    assert response.status_code == 422
    assert_private(response)
    if "ssn" in changes:
        assert changes["ssn"] not in response.text
    assert db.scalar(select(Employee.ssn)) is None
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"fed_extra_cents": -1},
        {"fed_extra_cents": 12.5},
        {"ca_allowances": 21},
        {"ca_allowances": -1},
        {"fed_filing_status": "invalid"},
    ],
)
def test_invalid_withholding_does_not_append(client, db, employee_context, changes):
    response = client.put("/api/me/withholding", json={**WITHHOLDING, **changes})
    assert response.status_code == 422
    assert db.scalar(select(func.count()).select_from(Withholding)) == 0
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 0


def test_invalid_bank_number_is_not_echoed_in_validation_response(client, db, employee_context):
    invalid = "private-account-number-12345"
    response = client.put("/api/me/bank-account", json={**BANK, "account_number": invalid})
    assert response.status_code == 422
    assert invalid not in response.text
    assert_private(response)
    assert db.scalar(select(func.count()).select_from(BankAccount)) == 0


@pytest.mark.parametrize(
    "endpoint,body", [("personal", PERSONAL), ("withholding", WITHHOLDING), ("bank-account", BANK)]
)
def test_mutation_and_audit_rollback_together(
    client, db, employee_context, monkeypatch, endpoint, body
):
    company, employee, _ = employee_context
    previous_bank = f.make_bank_account(db, company, employee=employee)

    def transactional_db():
        with Session(
            bind=db.connection(),
            join_transaction_mode="create_savepoint",
            autoflush=False,
            expire_on_commit=False,
        ) as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    original = audit.record

    def fail_after_record(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("audit transaction failed")

    app.dependency_overrides[get_db] = transactional_db
    monkeypatch.setattr(audit, "record", fail_after_record)
    with pytest.raises(RuntimeError, match="audit transaction failed"):
        client.put(f"/api/me/{endpoint}", json=body)
    db.expire_all()
    assert employee.ssn is None
    assert previous_bank.status == BankAccountStatus.VERIFIED
    assert db.scalar(select(func.count()).select_from(BankAccount)) == 1
    assert db.scalar(select(func.count()).select_from(Withholding)) == 0
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 0
