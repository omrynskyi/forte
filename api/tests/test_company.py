"""B-03: company onboarding, protected mutations, masked secrets and tenant isolation."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app import audit, clock
from app.adapters import get_bank_verifier
from app.adapters.bank import BankVerification
from app.db import get_db
from app.main import app
from app.models import AuditLog, BankAccount, Company, Membership, PayPeriod
from app.models.enums import BankAccountStatus, MembershipStatus, Role
from app.security.crypto import decrypt
from tests import factories as f

NOW = datetime(2026, 11, 25, 18, tzinfo=UTC)
PROFILE = {
    "legal_name": "Larkspur Bakery, Inc.",
    "ein": "12-3456789",
    "address": {"line1": "1180 Alder Street", "city": "San Jose", "state": "CA", "zip": "95112"},
}
BANK = {"routing_number": "110000000", "account_number": "000123453347", "account_type": "checking"}
SCHEDULE = {"schedule": "biweekly", "first_pay_date": "2026-12-11", "cutoff_lead_days": 2}


@pytest.fixture(autouse=True)
def frozen(monkeypatch):
    monkeypatch.setattr(clock, "now", lambda: NOW)


@pytest.fixture
def staff(db, as_actor):
    company = f.make_company(db)
    admin = f.make_member(db, company)
    as_actor(admin)
    return company, admin


def signup(client, db):
    user = f.make_user(db)
    response = client.post("/api/auth/dev/login", json={"email": user.email})
    assert response.status_code == 200
    return user


def test_create_company_real_cookie_and_encrypted_ein(client, db):
    user = signup(client, db)
    response = client.post("/api/companies", json=PROFILE)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["ein_last4"] == "6789"
    assert "ein" not in body
    assert body["address"] == {**PROFILE["address"], "line2": None}
    assert body["setup"] == {
        "company_profile": True,
        "funding_account": False,
        "pay_schedule": False,
        "team_invited": False,
        "complete": False,
    }
    member = db.scalars(select(Membership).where(Membership.user_id == user.id)).one()
    assert member.role == Role.ADMIN
    assert member.status == MembershipStatus.ACTIVE
    assert str(member.company_id) == body["id"]
    raw_ein = db.execute(
        text("SELECT ein FROM companies WHERE id = :id"), {"id": member.company_id}
    ).scalar_one()
    assert raw_ein != PROFILE["ein"]
    assert decrypt(raw_ein) == "123456789"
    entry = db.scalars(select(AuditLog).where(AuditLog.action == audit.COMPANY_CREATED)).one()
    assert entry.actor_membership_id == member.id
    assert entry.actor_user_id == user.id
    assert entry.company_id == member.company_id
    assert PROFILE["ein"] not in str(entry.after)
    assert "123456789" not in str(entry.after)
    assert client.get("/api/company").json() == body
    assert client.get("/api/auth/me").json()["membership"]["role"] == "admin"
    duplicate = client.post("/api/companies", json=PROFILE)
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "already_has_company"
    assert db.scalar(select(func.count()).select_from(Company)) == 1


@pytest.mark.parametrize("status", list(MembershipStatus))
def test_existing_membership_cannot_create_another_company(client, db, status):
    user = signup(client, db)
    company = f.make_company(db)
    db.add(Membership(company_id=company.id, user_id=user.id, role=Role.ADMIN, status=status))
    db.flush()
    response = client.post("/api/companies", json=PROFILE)
    assert response.status_code == 409
    assert db.scalar(select(func.count()).select_from(Company)) == 1


@pytest.mark.parametrize("ein", ["1234", "aa-1234567", "1234567890", "１２３４５６７８９"])
def test_invalid_ein(client, db, ein):
    signup(client, db)
    response = client.post("/api/companies", json={**PROFILE, "ein": ein})
    assert response.status_code == 422
    assert db.scalar(select(func.count()).select_from(Company)) == 0


def test_patch_company_and_masked_audit(client, db, staff):
    company, _ = staff
    response = client.patch(
        "/api/company",
        json={
            "legal_name": "Larkspur Test Bakery",
            "ein": "987654321",
            "address": {**PROFILE["address"], "line1": "22 Fake Lane", "line2": "Suite 2"},
        },
    )
    assert response.status_code == 200
    assert response.json()["ein_last4"] == "4321"
    assert response.json()["address"]["line2"] == "Suite 2"
    assert response.json()["address"]["line1"] == "22 Fake Lane"
    entry = db.scalars(select(AuditLog).where(AuditLog.action == audit.COMPANY_UPDATED)).one()
    assert entry.before["ein_last4"] == "6789"
    assert entry.after["ein_last4"] == "4321"
    assert "987654321" not in str(entry.after)
    assert client.patch("/api/company", json={"ein": "bad"}).status_code == 422
    assert (
        client.patch(
            "/api/company", json={"address": {**PROFILE["address"], "state": "NY"}}
        ).status_code
        == 422
    )


def test_funding_verification_replaces_only_company_account(client, db, staff):
    company, _ = staff
    previous = f.make_bank_account(db, company)
    employee = f.make_employee(db, company)
    employee_account = db.scalar(select(BankAccount).where(BankAccount.employee_id == employee.id))
    other, _ = f.other_company_setup(db)
    other_account = f.make_bank_account(db, other)
    response = client.put(
        "/api/company/funding-account", json={**BANK, "account_number": "000123459876"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["account_last4"] == "9876"
    assert body["status"] == "verified"
    assert "account_number" not in body
    db.refresh(previous)
    db.refresh(employee_account)
    db.refresh(other_account)
    assert previous.status == BankAccountStatus.REPLACED
    assert employee_account.status == other_account.status == BankAccountStatus.VERIFIED
    assert client.get("/api/company").json()["funding_account"]["id"] == body["id"]
    raw = db.execute(
        text("SELECT account_number FROM bank_accounts WHERE id = CAST(:id AS uuid)"),
        {"id": body["id"]},
    ).scalar_one()
    assert decrypt(raw) == "000123459876"
    entry = db.scalars(
        select(AuditLog).where(AuditLog.action == audit.FUNDING_ACCOUNT_CONNECTED)
    ).one()
    assert entry.before == {"account_last4": "3347"}
    assert entry.after == {"account_last4": "9876"}


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"routing_number": "123456789"}, "That routing number isn't valid."),
        ({"account_number": "12340000"}, "The bank couldn't confirm this account."),
    ],
)
def test_bank_failure_leaves_previous_funding_account(client, db, staff, changes, reason):
    company, _ = staff
    previous = f.make_bank_account(db, company)
    response = client.put("/api/company/funding-account", json={**BANK, **changes})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "bank_verification_failed"
    assert response.json()["detail"]["reason"] == reason
    db.refresh(previous)
    assert previous.status == BankAccountStatus.VERIFIED
    assert db.scalar(select(func.count()).select_from(BankAccount)) == 1
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 0


def test_bank_uses_injected_adapter(client, db, staff):
    calls = []

    class Verifier:
        def verify(self, routing_number, account_number):
            calls.append((routing_number, account_number))
            return BankVerification("verified", "test-provider-ref")

    app.dependency_overrides[get_bank_verifier] = Verifier
    response = client.put("/api/company/funding-account", json=BANK)
    assert response.status_code == 200
    assert calls == [(BANK["routing_number"], BANK["account_number"])]
    assert db.scalar(select(BankAccount.provider_ref)) == "test-provider-ref"


def test_setup_completion_when_all_four_done_is_set_once(client, db, staff, monkeypatch):
    company, admin = staff
    company.pay_schedule = None
    company.first_pay_date = None
    db.flush()
    assert not client.get("/api/company").json()["setup"]["complete"]
    assert client.put("/api/company/funding-account", json=BANK).status_code == 200
    assert client.put("/api/company/pay-schedule", json=SCHEDULE).status_code == 200
    assert company.setup_completed_at is None
    invited = f.make_member(db, company, Role.PAYROLL_MANAGER, status=MembershipStatus.INVITED)
    response = client.get("/api/company")
    assert response.json()["setup"] == {
        "company_profile": True,
        "funding_account": True,
        "pay_schedule": True,
        "team_invited": True,
        "complete": True,
    }
    assert company.setup_completed_at == NOW
    monkeypatch.setattr(clock, "now", lambda: NOW + timedelta(hours=1))
    assert client.get("/api/company").json()["setup"]["complete"]
    assert company.setup_completed_at == NOW
    invited.status = MembershipStatus.REMOVED
    db.flush()
    assert not client.get("/api/company").json()["setup"]["team_invited"]
    assert company.setup_completed_at == NOW


def test_schedule_endpoint_and_lazy_topup(client, db, staff, monkeypatch):
    company, _ = staff
    response = client.put("/api/company/pay-schedule", json=SCHEDULE)
    assert response.status_code == 200
    periods = response.json()
    assert len(periods) == 6
    assert periods[0]["start_date"] == "2026-11-23"
    assert periods[0]["end_date"] == "2026-12-06"
    assert periods[0]["cutoff_at"].replace("+00:00", "Z") == "2026-12-10T01:00:00Z"
    assert periods[0]["regular_run_id"] is None
    listed = client.get("/api/pay-periods")
    assert listed.status_code == 200
    assert listed.json() == periods
    entry = db.scalars(select(AuditLog).where(AuditLog.action == audit.PAY_SCHEDULE_SET)).one()
    assert entry.company_id == company.id
    monkeypatch.setattr(clock, "now", lambda: datetime(2027, 1, 10, 18, tzinfo=UTC))
    periods = client.get("/api/pay-periods").json()
    assert len([p for p in periods if p["pay_date"] >= "2027-01-10"]) == 6
    assert [p["pay_date"] for p in periods] == sorted(p["pay_date"] for p in periods)


@pytest.mark.parametrize(
    "changes",
    [
        {"first_pay_date": "2026-11-28"},
        {"first_pay_date": "2026-11-26"},
        {"first_pay_date": "2026-11-24"},
        {"cutoff_lead_days": 0},
        {"cutoff_lead_days": 4},
        {"schedule": "weekly"},
    ],
)
def test_schedule_validation_does_not_write(client, db, staff, changes):
    company, _ = staff
    response = client.put("/api/company/pay-schedule", json={**SCHEDULE, **changes})
    assert response.status_code == 422
    assert db.scalar(select(func.count()).select_from(PayPeriod)) == 0
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 0


@pytest.mark.parametrize(
    "role,status",
    [
        (Role.PAYROLL_MANAGER, MembershipStatus.ACTIVE),
        (Role.EMPLOYEE, MembershipStatus.ACTIVE),
        (Role.ADMIN, MembershipStatus.FORMER),
    ],
)
def test_permissions(client, db, as_actor, role, status):
    company = f.make_company(db)
    as_actor(f.make_member(db, company, role, status=status))
    read_status = 200 if role == Role.PAYROLL_MANAGER else 403
    assert client.get("/api/company").status_code == read_status
    assert client.get("/api/pay-periods").status_code == read_status
    assert client.patch("/api/company", json={"legal_name": "Changed"}).status_code == 403
    assert client.put("/api/company/funding-account", json=BANK).status_code == 403
    assert client.put("/api/company/pay-schedule", json=SCHEDULE).status_code == 403


def test_company_and_mutations_cannot_target_other_tenant(client, db, staff):
    company, _ = staff
    other, _ = f.other_company_setup(db)
    other_account = f.make_bank_account(db, other)
    payload = {"company_id": str(other.id), "legal_name": "Changed own company"}
    response = client.patch("/api/company", json=payload)
    assert response.status_code == 200
    assert response.json()["id"] == str(company.id)
    db.refresh(other)
    assert other.legal_name != payload["legal_name"]
    assert (
        client.put(
            "/api/company/funding-account", json={**BANK, "company_id": str(other.id)}
        ).status_code
        == 200
    )
    db.refresh(other_account)
    assert other_account.status == BankAccountStatus.VERIFIED
    assert (
        client.put(
            "/api/company/pay-schedule", json={**SCHEDULE, "company_id": str(other.id)}
        ).status_code
        == 200
    )
    own_period_ids = {
        p.id for p in db.scalars(select(PayPeriod).where(PayPeriod.company_id == company.id))
    }
    assert {p["id"] for p in client.get("/api/pay-periods").json()} == {
        str(i) for i in own_period_ids
    }
    assert (
        db.scalar(
            select(func.count()).select_from(PayPeriod).where(PayPeriod.company_id == other.id)
        )
        == 0
    )


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("post", "/api/companies", PROFILE),
        ("get", "/api/company", None),
        ("patch", "/api/company", {"legal_name": "Changed"}),
        ("put", "/api/company/funding-account", BANK),
        ("put", "/api/company/pay-schedule", SCHEDULE),
        ("get", "/api/pay-periods", None),
    ],
)
def test_unauthenticated_requests(client, method, path, body):
    response = (
        client.request(method, path, json=body)
        if body is not None
        else client.request(method, path)
    )
    assert response.status_code == 401


def test_funding_replacement_and_audit_rollback_together(client, db, staff, monkeypatch):
    company, _ = staff
    previous = f.make_bank_account(db, company)

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

    def fail_response(*args):
        raise RuntimeError("response failure")

    app.dependency_overrides[get_db] = transactional_db
    monkeypatch.setattr("app.routers.company._company_out", fail_response)
    with pytest.raises(RuntimeError, match="response failure"):
        client.put("/api/company/funding-account", json={**BANK, "account_number": "000123459876"})
    db.expire_all()
    assert previous.status == BankAccountStatus.VERIFIED
    assert db.scalar(select(func.count()).select_from(BankAccount)) == 1
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 0
