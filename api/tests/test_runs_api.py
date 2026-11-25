"""A-04: runs API workflow, response contract, permissions and tenant isolation."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app import clock
from app.adapters import get_tax_provider
from app.adapters.tax import TaxProviderError
from app.models import AuditLog, PayrollItem, PayrollRun, TimeEntry, Timesheet
from app.models.enums import MembershipStatus, Role, RunState, RunType, TimesheetStatus
from tests import factories as f

NOW = datetime(2026, 12, 7, 18, tzinfo=UTC)


@pytest.fixture
def setup(db, as_actor, monkeypatch):
    monkeypatch.setattr(clock, "now", lambda: NOW)
    company = f.make_company(db)
    period = f.make_pay_period(db, company, cutoff_at=NOW + timedelta(hours=3))
    employee = f.make_employee(db, company)
    manager = f.make_member(db, company, Role.PAYROLL_MANAGER, employee=employee)
    admin = f.make_member(db, company, Role.ADMIN, email="admin@larkspur.example")
    sheet = Timesheet(
        company_id=company.id,
        employee_id=employee.id,
        pay_period_id=period.id,
        status=TimesheetStatus.APPROVED,
    )
    db.add(sheet)
    db.flush()
    db.add(
        TimeEntry(
            company_id=company.id, timesheet_id=sheet.id, work_date=period.start_date, minutes=480
        )
    )
    db.flush()
    as_actor(manager)
    return company, period, employee, manager, admin, sheet


def create(client, period):
    response = client.post(
        "/api/runs", json={"run_type": "regular", "pay_period_id": str(period.id)}
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_manager_to_admin_flow(client, db, as_actor, setup):
    company, period, employee, manager, admin, sheet = setup
    run = create(client, period)
    run_id = run["id"]
    assert run["state"] == "draft"
    assert run["created_by_name"] == "Devon Park"
    assert run["employee_count"] == 1
    item = run["items"][0]
    assert item["employee_name"] == "Devon Park"
    assert item["is_caller"] is True
    assert item["minutes"] == 480
    assert item["gross_cents"] == 19600
    assert run["totals"]["gross_cents"] == item["gross_cents"]
    assert run["totals"]["employee_taxes_cents"] == sum(item["taxes"].values())
    assert run["totals"]["company_cost_cents"] == item["employer_cost_cents"]
    assert run["allowed_actions"] == ["submit"]
    assert run["blockers"] == []
    assert run["timesheets_unapproved"] == 0
    submitted = client.post(f"/api/runs/{run_id}/submit", json={"note": "Ready for review"})
    assert submitted.status_code == 200
    assert submitted.json()["submitted_by_name"] == "Devon Park"
    assert submitted.json()["allowed_actions"] == ["return_to_draft"]
    db.refresh(sheet)
    assert sheet.status == TimesheetStatus.LOCKED
    assert client.post(f"/api/runs/{run_id}/approve", json={}).status_code == 403
    as_actor(admin)
    detail = client.get(f"/api/runs/{run_id}").json()
    assert set(detail["allowed_actions"]) == {"approve", "cancel", "return_to_draft"}
    assert detail["items"][0]["is_caller"] is False
    approved = client.post(f"/api/runs/{run_id}/approve", json={})
    assert approved.status_code == 200
    assert approved.json()["state"] == "approved"
    assert approved.json()["approved_by_name"] == "admin@larkspur.example"
    assert approved.json()["allowed_actions"] == []
    audits = db.scalars(select(AuditLog).where(AuditLog.entity_id == run_id)).all()
    assert {a.action for a in audits} >= {"run.recalculated", "run.transitioned"}
    assert any(a.after.get("note") == "Ready for review" for a in audits)


@pytest.mark.parametrize("action", ["return-to-draft", "cancel"])
def test_unlocks_submitted_sheets(client, db, as_actor, setup, action):
    _, period, _, _, admin, sheet = setup
    run_id = create(client, period)["id"]
    assert client.post(f"/api/runs/{run_id}/submit", json={}).status_code == 200
    if action == "cancel":
        assert client.post(f"/api/runs/{run_id}/cancel", json={}).status_code == 403
        as_actor(admin)
    response = client.post(f"/api/runs/{run_id}/{action}", json={})
    assert response.status_code == 200
    db.refresh(sheet)
    assert sheet.status == TimesheetStatus.APPROVED
    if action == "return-to-draft":
        assert response.json()["submitted_by_name"] is None
        assert response.json()["submitted_at"] is None
        assert client.post(f"/api/runs/{run_id}/submit", json={}).status_code == 200
    else:
        assert response.json()["state"] == "cancelled"
        assert create(client, period)["id"] != run_id


def test_duplicate_and_invalid_creation(client, setup):
    _, period, *_ = setup
    create(client, period)
    response = client.post(
        "/api/runs", json={"run_type": "regular", "pay_period_id": str(period.id)}
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "run_exists"
    assert client.post("/api/runs", json={"run_type": "regular"}).status_code == 422
    assert (
        client.post("/api/runs", json={"run_type": "regular", "pay_period_id": "bad"}).status_code
        == 422
    )
    response = client.post("/api/runs", json={"run_type": "bonus"})
    assert response.status_code == 501
    assert response.json()["detail"]["task"] == "A-11"


def test_recalculate_and_read_only_get(client, db, setup):
    _, period, _, _, _, sheet = setup
    run = create(client, period)
    entry = db.scalars(select(TimeEntry).where(TimeEntry.timesheet_id == sheet.id)).one()
    entry.minutes = 600
    db.flush()
    assert client.get(f"/api/runs/{run['id']}").json()["totals"] == run["totals"]
    response = client.post(f"/api/runs/{run['id']}/recalculate")
    assert response.status_code == 200
    assert response.json()["items"][0]["gross_cents"] == 24500
    assert client.post(f"/api/runs/{run['id']}/submit", json={}).status_code == 200
    assert client.post(f"/api/runs/{run['id']}/recalculate").status_code == 409


def test_warnings_and_cutoff(client, db, as_actor, setup):
    company, period, _, _, admin, _ = setup
    missing = f.make_employee(db, company, "Mia", "Novak", onboarded=False)
    f.make_employee(db, company, "Lee", "Ito")  # no timesheet
    rejected = f.make_employee(db, company, "Bo", "Chen")
    db.add(
        Timesheet(
            company_id=company.id,
            employee_id=rejected.id,
            pay_period_id=period.id,
            status=TimesheetStatus.REJECTED,
        )
    )
    db.flush()
    run = create(client, period)
    assert run["blockers"][0]["employee_id"] == str(missing.id)
    assert set(run["blockers"][0]["missing"]) == {"personal_info", "withholding", "bank_account"}
    assert run["timesheets_unapproved"] == 3
    assert not run["at_risk"]
    client.post(f"/api/runs/{run['id']}/submit", json={})
    period.cutoff_at = NOW
    db.flush()
    as_actor(admin)
    response = client.get(f"/api/runs/{run['id']}").json()
    assert response["at_risk"]
    assert "approve" not in response["allowed_actions"]
    response = client.post(f"/api/runs/{run['id']}/approve", json={})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "past_cutoff"


def test_empty_run_and_separation_of_duties(client, db, as_actor, setup):
    _, period, _, _, admin, sheet = setup
    sheet.status = TimesheetStatus.OPEN
    db.flush()
    run_id = create(client, period)["id"]
    response = client.post(f"/api/runs/{run_id}/submit", json={})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "empty_run"
    sheet.status = TimesheetStatus.APPROVED
    db.flush()
    client.post(f"/api/runs/{run_id}/recalculate")
    as_actor(admin)
    client.post(f"/api/runs/{run_id}/submit", json={})
    assert "approve" not in client.get(f"/api/runs/{run_id}").json()["allowed_actions"]
    response = client.post(f"/api/runs/{run_id}/approve", json={})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "separation_of_duties"


def test_list_order_filters_and_tenant(client, db, as_actor, setup):
    company, period, _, _, admin, _ = setup
    first = create(client, period)
    later = f.make_pay_period(db, company, date(2026, 12, 25))
    second = create(client, later)
    bonus = f.make_run(db, company, run_type=RunType.BONUS)
    other, _ = f.other_company_setup(db)
    f.make_run(db, other)
    runs = client.get("/api/runs?run_type=regular&state=draft").json()
    assert [r["id"] for r in runs] == [second["id"], first["id"]]
    as_actor(admin)
    client.post(f"/api/runs/{first['id']}/cancel", json={})
    runs = client.get("/api/runs?state=cancelled").json()
    assert [r["id"] for r in runs] == [first["id"]]
    assert runs[0]["at_risk"] is False
    summary = client.get("/api/runs?run_type=bonus").json()[0]
    assert summary["id"] == str(bonus.id)
    assert summary["cutoff_at"] is None
    assert summary["period_start"] is None


@pytest.mark.parametrize(
    "action", [None, "recalculate", "submit", "return-to-draft", "cancel", "approve"]
)
@pytest.mark.parametrize("missing", [False, True])
def test_id_routes_hide_other_tenants_and_missing_runs(
    client, db, as_actor, setup, action, missing
):
    _, _, _, _, admin, _ = setup
    as_actor(admin)
    other, _ = f.other_company_setup(db)
    run = f.make_run(db, other)
    run_id = uuid.uuid4() if missing else run.id
    url = f"/api/runs/{run_id}"
    response = client.get(url) if action is None else client.post(f"{url}/{action}", json={})
    assert response.status_code == 404


def test_create_hides_foreign_period(client, db, setup):
    other, _ = f.other_company_setup(db)
    period = f.make_pay_period(db, other)
    response = client.post(
        "/api/runs", json={"run_type": "regular", "pay_period_id": str(period.id)}
    )
    assert response.status_code == 404


@pytest.mark.parametrize(
    "role,status", [(Role.EMPLOYEE, MembershipStatus.ACTIVE), (Role.ADMIN, MembershipStatus.FORMER)]
)
def test_disallowed_members(client, db, as_actor, setup, role, status):
    company, period, *_ = setup
    run_id = create(client, period)["id"]
    as_actor(f.make_member(db, company, role, status=status))
    assert client.get("/api/runs").status_code == 403
    assert client.get(f"/api/runs/{run_id}").status_code == 403
    for action in ("recalculate", "submit", "return-to-draft", "cancel", "approve"):
        assert client.post(f"/api/runs/{run_id}/{action}", json={}).status_code == 403
    assert (
        client.post(
            "/api/runs", json={"run_type": "regular", "pay_period_id": str(period.id)}
        ).status_code
        == 403
    )


def test_no_actor_uses_auth_dependency(client):
    assert client.get("/api/runs").status_code in (401, 501)


def test_tax_failure_does_not_change_existing_pay(client, db, setup):
    _, period, *_ = setup
    run = create(client, period)

    class DownTax:
        def calculate(self, requests):
            raise TaxProviderError("offline")

    from app.main import app

    app.dependency_overrides[get_tax_provider] = DownTax
    response = client.post(f"/api/runs/{run['id']}/recalculate")
    assert response.status_code == 503
    assert client.get(f"/api/runs/{run['id']}").json()["items"] == run["items"]
    assert db.scalar(select(PayrollItem.id).where(PayrollItem.run_id == uuid.UUID(run["id"])))
    assert db.get(PayrollRun, uuid.UUID(run["id"])).state == RunState.DRAFT
