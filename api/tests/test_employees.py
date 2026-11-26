"""B-05: staff employee management, invitations, pay history and audited sensitive reveals."""

import uuid
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app import audit, clock
from app.db import get_db
from app.main import app
from app.models import (
    AuditLog,
    Compensation,
    Employee,
    MagicLinkToken,
    Membership,
    Notification,
    User,
)
from app.models.enums import MembershipStatus, Role
from app.services.readiness import current_compensation
from tests import factories as f

NOW = datetime(2026, 11, 25, 18, tzinfo=UTC)
CREATE = {
    "first_name": "Devon",
    "last_name": "Park",
    "email": "devon-new@larkspur.example",
    "job_title": "Counter staff",
    "hire_date": "2026-11-25",
    "compensation": {"pay_type": "hourly", "amount_cents": 2450, "effective_date": "2026-11-25"},
}
COMP = {"pay_type": "hourly", "amount_cents": 2550, "effective_date": "2026-11-25"}


@pytest.fixture(autouse=True)
def frozen(monkeypatch):
    monkeypatch.setattr(clock, "now", lambda: NOW)


@pytest.fixture
def staff(db, as_actor):
    company = f.make_company(db)
    manager = f.make_member(db, company, Role.PAYROLL_MANAGER)
    as_actor(manager)
    return company, manager


def test_manager_creates_employee_with_compensation_and_invite(client, db, staff, outbox):
    company, manager = staff
    response = client.post("/api/employees", json=CREATE)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["employee_number"] == 1
    assert data["email"] == CREATE["email"]
    assert data["membership_status"] == "invited"
    assert data["role"] == "employee"
    assert data["compensation"]["amount_cents"] == 2450
    assert data["compensation"]["is_current"] is True
    assert data["compensation"]["set_by_name"] == db.get(User, manager.user_id).email
    assert data["ready"] is False
    assert set(data["missing"]) == {"personal_info", "withholding", "bank_account"}
    assert data["address"] is None
    assert data["withholding"] is None
    assert data["deposit_account"] is None
    employee = db.get(Employee, uuid.UUID(data["id"]))
    assert employee.company_id == company.id
    member = db.scalars(select(Membership).where(Membership.employee_id == employee.id)).one()
    assert member.invited_by_membership_id == manager.id
    assert member.status == MembershipStatus.INVITED
    assert member.role == Role.EMPLOYEE
    assert len(outbox.outbox) == 1
    to, subject, body = outbox.outbox[0]
    assert to == CREATE["email"]
    assert "invitation" in subject.lower()
    assert "works once, for 15 minutes" in body
    notification = db.scalars(
        select(Notification).where(Notification.user_id == member.user_id)
    ).one()
    assert notification.kind == "invite"
    assert notification.company_id == company.id
    assert notification.sent_at == NOW
    assert db.scalars(select(MagicLinkToken).where(MagicLinkToken.user_id == member.user_id)).one()
    actions = {row.action for row in db.scalars(select(AuditLog))}
    assert actions == {audit.EMPLOYEE_CREATED, audit.COMPENSATION_SET, audit.MEMBER_INVITED}
    for row in db.scalars(select(AuditLog)):
        assert row.company_id == company.id
        assert row.actor_membership_id == manager.id
    # The invitation can be redeemed through B-01/B-02 without B-06 being merged.
    token = parse_qs(urlparse(body.split("Sign in to Forte: ")[1].split()[0]).query)["token"][0]
    verified = client.post("/api/auth/verify", json={"token": token})
    assert verified.status_code == 200
    assert verified.json()["employee_id"] == data["id"]
    assert verified.json()["membership"]["status"] == "active"
    assert client.get("/api/auth/me").json()["employee_id"] == data["id"]


def test_employee_numbers_continue_from_company_max_and_lock_company(client, db, staff):
    company, _ = staff
    previous = f.make_employee(db, company)
    previous.employee_number = 17
    other, _ = f.other_company_setup(db)
    foreign = f.make_employee(db, other)
    foreign.employee_number = 200
    db.flush()
    statements = []
    connection = db.connection()

    def capture(conn, cursor, statement, *args):
        statements.append(statement)

    event.listen(connection, "before_cursor_execute", capture)
    try:
        first = client.post("/api/employees", json=CREATE)
    finally:
        event.remove(connection, "before_cursor_execute", capture)
    assert first.status_code == 201
    assert first.json()["employee_number"] == 18
    assert any("FROM companies" in sql and "FOR UPDATE" in sql for sql in statements)
    second = client.post("/api/employees", json={**CREATE, "email": "another@larkspur.example"})
    assert second.status_code == 201
    assert second.json()["employee_number"] == 19


def test_existing_user_without_membership_is_reused(client, db, staff):
    user = f.make_user(db, CREATE["email"])
    response = client.post("/api/employees", json={**CREATE, "email": CREATE["email"].upper()})
    assert response.status_code == 201
    assert response.json()["email"] == CREATE["email"]
    assert (
        db.scalar(
            select(Membership.user_id).where(
                Membership.employee_id == uuid.UUID(response.json()["id"])
            )
        )
        == user.id
    )
    assert (
        db.scalar(select(func.count()).select_from(User).where(User.email == CREATE["email"])) == 1
    )


@pytest.mark.parametrize("foreign", [False, True])
def test_existing_membership_conflict_does_not_change_roles(client, db, staff, foreign):
    company, _ = staff
    if foreign:
        company, _ = f.other_company_setup(db)
    existing = f.make_member(db, company, Role.ADMIN, email=CREATE["email"])
    response = client.post("/api/employees", json=CREATE)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "email_in_use"
    assert response.json()["detail"]["message"] == "This email cannot be used for a new employee."
    db.refresh(existing)
    assert existing.role == Role.ADMIN
    assert existing.employee_id is None
    assert db.scalar(select(func.count()).select_from(Employee)) == 0


def test_duplicate_employee_email_is_case_insensitive(client, db, staff):
    assert client.post("/api/employees", json=CREATE).status_code == 201
    duplicate = client.post("/api/employees", json={**CREATE, "email": CREATE["email"].upper()})
    assert duplicate.status_code == 409
    assert db.scalar(select(func.count()).select_from(Employee)) == 1


def test_list_detail_readiness_and_masking(client, db, staff):
    company, _ = staff
    employee = f.make_employee(db, company)
    member = f.make_member(db, company, Role.EMPLOYEE, employee=employee)
    incomplete = f.make_employee(db, company, "Mia", "Novak", onboarded=False)
    other, _ = f.other_company_setup(db)
    foreign = f.make_employee(db, other)
    detail = client.get(f"/api/employees/{employee.id}")
    assert detail.status_code == 200
    data = detail.json()
    assert data["ready"] is True and data["missing"] == []
    assert data["ssn_last4"] == "4821"
    assert data["deposit_account"]["account_last4"] == "3347"
    assert data["withholding"]["fed_filing_status"] == "single"
    assert data["membership_status"] == member.status.value
    assert data["role"] == "employee"
    assert data["compensation"]["set_by_name"] is None
    assert data["address"]["city"] == "San Jose"
    listed = client.get("/api/employees")
    assert listed.status_code == 200
    by_id = {row["id"]: row for row in listed.json()}
    assert str(foreign.id) not in by_id
    assert by_id[str(employee.id)]["ready"] is True
    assert by_id[str(employee.id)]["pay_amount_cents"] == 2450
    assert by_id[str(incomplete.id)]["ready"] is False
    assert set(by_id[str(incomplete.id)]["missing"]) == {
        "personal_info",
        "withholding",
        "bank_account",
    }
    for response in (detail, listed):
        assert response.headers["cache-control"] == "no-store"
        for secret in ("123-45-4821", "123454821", "000123453347"):
            assert secret not in response.text


def test_update_employee_and_audit(client, db, staff):
    company, _ = staff
    employee = f.make_employee(db, company)
    response = client.patch(
        f"/api/employees/{employee.id}",
        json={
            "first_name": "Devon Updated",
            "job_title": "Shift lead",
            "amount_cents": 999999,
            "email": "ignored@larkspur.example",
            "status": "terminated",
        },
    )
    assert response.status_code == 200
    assert response.json()["first_name"] == "Devon Updated"
    assert response.json()["job_title"] == "Shift lead"
    assert response.json()["status"] == "active"
    assert response.json()["email"] == employee.email
    assert response.json()["compensation"]["amount_cents"] == 2450
    entry = db.scalars(select(AuditLog).where(AuditLog.action == audit.EMPLOYEE_UPDATED)).one()
    assert entry.before["job_title"] == "Counter lead"
    assert entry.after["job_title"] == "Shift lead"


def test_compensation_history_current_and_future_versions(client, db, staff):
    employee_id = client.post("/api/employees", json=CREATE).json()["id"]
    now = client.post(f"/api/employees/{employee_id}/compensations", json=COMP)
    assert now.status_code == 201
    future = client.post(
        f"/api/employees/{employee_id}/compensations",
        json={**COMP, "amount_cents": 2700, "effective_date": "2027-01-01"},
    )
    assert future.status_code == 201
    assert not future.json()["is_current"]
    history = client.get(f"/api/employees/{employee_id}/compensations").json()
    assert [row["amount_cents"] for row in history] == [2700, 2550, 2450]
    assert [row["is_current"] for row in history] == [False, True, False]
    assert (
        client.get(f"/api/employees/{employee_id}").json()["compensation"]["id"] == now.json()["id"]
    )
    assert (
        current_compensation(db, uuid.UUID(employee_id), clock.today_pacific()).amount_cents == 2550
    )
    # None of the older compensation rows was overwritten.
    assert db.scalar(select(func.count()).select_from(Compensation)) == 3


def test_history_set_by_uses_staff_employee_name(client, db, staff, as_actor):
    company, _ = staff
    staff_employee = f.make_employee(db, company, "Ana", "Reyes")
    manager = f.make_member(db, company, Role.PAYROLL_MANAGER, employee=staff_employee)
    as_actor(manager)
    response = client.post("/api/employees", json=CREATE)
    assert response.status_code == 201
    assert response.json()["compensation"]["set_by_name"] == "Ana Reyes"


@pytest.mark.parametrize("role", [Role.ADMIN, Role.PAYROLL_MANAGER])
def test_own_pay_and_title_changes_rejected_but_own_name_allowed(client, db, staff, as_actor, role):
    company, _ = staff
    employee = f.make_employee(db, company)
    manager = f.make_member(db, company, role, employee=employee)
    as_actor(manager)
    pay = client.post(f"/api/employees/{employee.id}/compensations", json=COMP)
    assert pay.status_code == 403
    assert pay.json()["detail"]["code"] == "own_compensation"
    title = client.patch(f"/api/employees/{employee.id}", json={"job_title": "CEO"})
    assert title.status_code == 403
    assert title.json()["detail"]["code"] == "own_job_title"
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 0
    assert (
        client.patch(f"/api/employees/{employee.id}", json={"first_name": "Ana"}).status_code == 200
    )
    assert client.get(f"/api/employees/{employee.id}").json()["job_title"] == "Counter lead"


@pytest.mark.parametrize(
    "field,expected", [("ssn", "123-45-4821"), ("bank_account_number", "000123453347")]
)
def test_reveal_returns_secret_but_audits_only_last4(client, db, staff, field, expected):
    company, manager = staff
    employee = f.make_employee(db, company)
    response = client.post(f"/api/employees/{employee.id}/reveal", json={"field": field})
    assert response.status_code == 200
    assert response.json() == {"field": field, "value": expected}
    assert response.headers["cache-control"] == "no-store"
    entry = db.scalars(
        select(AuditLog).where(AuditLog.action == audit.SENSITIVE_FIELD_REVEALED)
    ).one()
    assert entry.actor_membership_id == manager.id
    assert entry.company_id == company.id
    assert entry.after == {"field": field, "last4": expected[-4:]}
    assert expected not in str(entry.after)
    assert entry.before is None


@pytest.mark.parametrize("field", ["ssn", "bank_account_number"])
def test_missing_secret_returns_404_without_reveal_audit(client, db, staff, field):
    company, _ = staff
    employee = f.make_employee(db, company, onboarded=False)
    response = client.post(f"/api/employees/{employee.id}/reveal", json={"field": field})
    assert response.status_code == 404
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 0


@pytest.mark.parametrize("action", ["detail", "update", "history", "compensation", "reveal"])
@pytest.mark.parametrize("missing", [False, True])
def test_every_id_route_hides_other_company_and_missing_records(client, db, staff, action, missing):
    other, _ = f.other_company_setup(db)
    employee = f.make_employee(db, other)
    employee_id = uuid.uuid4() if missing else employee.id
    url = f"/api/employees/{employee_id}"
    if action == "detail":
        response = client.get(url)
    elif action == "update":
        response = client.patch(url, json={"job_title": "Changed"})
    elif action == "history":
        response = client.get(f"{url}/compensations")
    elif action == "compensation":
        response = client.post(f"{url}/compensations", json=COMP)
    else:
        response = client.post(f"{url}/reveal", json={"field": "ssn"})
    assert response.status_code == 404
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 0


@pytest.mark.parametrize("former", [False, True])
def test_employee_and_former_staff_cannot_use_staff_routes(client, db, as_actor, former):
    company = f.make_company(db)
    employee = f.make_employee(db, company)
    member = f.make_member(
        db,
        company,
        Role.ADMIN if former else Role.EMPLOYEE,
        employee=employee,
        status=MembershipStatus.FORMER if former else MembershipStatus.ACTIVE,
    )
    as_actor(member)
    url = f"/api/employees/{employee.id}"
    assert client.get("/api/employees").status_code == 403
    assert client.post("/api/employees", json=CREATE).status_code == 403
    assert client.get(url).status_code == 403
    assert client.patch(url, json={"job_title": "Changed"}).status_code == 403
    assert client.get(f"{url}/compensations").status_code == 403
    assert client.post(f"{url}/compensations", json=COMP).status_code == 403
    assert client.post(f"{url}/reveal", json={"field": "ssn"}).status_code == 403


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("get", "/api/employees", None),
        ("post", "/api/employees", CREATE),
        ("get", "/api/employees/{id}", None),
        ("patch", "/api/employees/{id}", {"job_title": "Changed"}),
        ("get", "/api/employees/{id}/compensations", None),
        ("post", "/api/employees/{id}/compensations", COMP),
        ("post", "/api/employees/{id}/reveal", {"field": "ssn"}),
    ],
)
def test_unauthenticated_requests(client, method, path, body):
    path = path.replace("{id}", str(uuid.uuid4()))
    response = client.request(method, path, json=body) if body else client.request(method, path)
    assert response.status_code == 401


@pytest.mark.parametrize(
    "changes",
    [
        {"email": "invalid"},
        {"compensation": {**COMP, "amount_cents": 0}},
        {"compensation": {**COMP, "amount_cents": 12.5}},
        {"hire_date": "bad"},
    ],
)
def test_invalid_create_does_not_write(client, db, staff, changes):
    response = client.post("/api/employees", json={**CREATE, **changes})
    assert response.status_code == 422
    assert db.scalar(select(func.count()).select_from(Employee)) == 0
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 0


def test_mail_failure_rolls_back_employee_comp_membership_and_audit(
    client, db, staff, outbox, monkeypatch
):
    def request_db():
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

    def fail_send(*args):
        raise RuntimeError("mail unavailable")

    app.dependency_overrides[get_db] = request_db
    monkeypatch.setattr(outbox, "send", fail_send)
    with pytest.raises(RuntimeError, match="mail unavailable"):
        client.post("/api/employees", json=CREATE)
    assert db.scalar(select(func.count()).select_from(Employee)) == 0
    assert db.scalar(select(func.count()).select_from(Compensation)) == 0
    assert db.scalar(select(func.count()).select_from(Membership)) == 1  # original PM only
    assert (
        db.scalar(select(func.count()).select_from(User).where(User.email == CREATE["email"])) == 0
    )
    assert db.scalar(select(func.count()).select_from(MagicLinkToken)) == 0
    assert db.scalar(select(func.count()).select_from(Notification)) == 0
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 0


@pytest.mark.parametrize("action", ["compensation", "update", "reveal"])
def test_audit_failure_rolls_back_mutation_and_prevents_reveal(
    client, db, staff, monkeypatch, action
):
    company, _ = staff
    employee = f.make_employee(db, company)
    original_title = employee.job_title
    original_pay_count = db.scalar(select(func.count()).select_from(Compensation))

    def request_db():
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

    def fail_record(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("audit unavailable")

    app.dependency_overrides[get_db] = request_db
    monkeypatch.setattr(audit, "record", fail_record)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        if action == "compensation":
            client.post(f"/api/employees/{employee.id}/compensations", json=COMP)
        elif action == "update":
            client.patch(f"/api/employees/{employee.id}", json={"job_title": "Changed"})
        else:
            client.post(f"/api/employees/{employee.id}/reveal", json={"field": "ssn"})
    db.expire_all()
    assert employee.job_title == original_title
    assert db.scalar(select(func.count()).select_from(Compensation)) == original_pay_count
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 0
