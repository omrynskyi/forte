"""B-07: daily minutes, reviews, company boundaries and payroll-submission locking."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from threading import Barrier, Event

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema, DropSchema

from app import audit, clock
from app.db import get_db
from app.errors import AppError
from app.main import app
from app.models import AuditLog, PayrollRun, TimeEntry, Timesheet, User
from app.models.base import Base
from app.models.enums import (
    EmploymentStatus,
    MembershipStatus,
    PayType,
    Role,
    RunState,
    TimesheetStatus,
)
from app.payroll.state_machine import transition
from app.payroll.states import RunAction
from app.routers.timesheets import my_timesheet, reject_timesheet
from app.schemas.timesheets import ReviewIn
from app.services.timesheets import approved_minutes, lock_for_period
from tests import factories as f

NOW = datetime(2026, 11, 26, 18, tzinfo=UTC)
DAY = "2026-11-25"


@pytest.fixture(autouse=True)
def frozen(monkeypatch):
    monkeypatch.setattr(clock, "now", lambda: NOW)


@pytest.fixture
def context(db, as_actor):
    company = f.make_company(db)
    period = f.make_pay_period(db, company, cutoff_at=NOW + timedelta(days=10))
    employee = f.make_employee(db, company)
    member = f.make_member(db, company, Role.EMPLOYEE, employee=employee)
    manager = f.make_member(db, company, Role.PAYROLL_MANAGER)
    admin = f.make_member(db, company)
    as_actor(member)
    return company, period, employee, member, manager, admin


def put(client, minutes=480, day=DAY):
    return client.put(
        "/api/me/timesheet/entries", json={"entries": [{"work_date": day, "minutes": minutes}]}
    )


def test_lazy_get_and_staff_list_share_one_sheet(client, db, context, as_actor):
    _, period, employee, _, manager, _ = context
    first = client.get("/api/me/timesheet")
    assert first.status_code == 200
    data = first.json()
    assert data["employee_id"] == str(employee.id)
    assert data["employee_name"] == "Devon Park"
    assert data["pay_period"]["id"] == str(period.id)
    assert data["status"] == "open" and data["editable"] is True
    assert data["rate_cents"] == 2450
    assert data["entries"] == [] and data["total_minutes"] == 0
    assert client.get("/api/me/timesheet").json()["id"] == data["id"]
    as_actor(manager)
    listed = client.get("/api/timesheets")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == data["id"]
    assert listed.json()[0]["editable"] is False
    assert db.scalar(select(func.count()).select_from(Timesheet)) == 1


def test_upsert_delete_zero_and_preserve_unspecified_days(client, db, context):
    response = client.put(
        "/api/me/timesheet/entries",
        json={
            "entries": [
                {"work_date": DAY, "minutes": 480},
                {"work_date": "2026-11-26", "minutes": 300},
            ]
        },
    )
    assert response.status_code == 200
    assert response.json()["total_minutes"] == 780
    original_id = response.json()["entries"][0]["id"]
    response = put(client, 600)
    assert response.status_code == 200
    assert response.json()["total_minutes"] == 900
    assert response.json()["entries"][0]["id"] == original_id
    response = put(client, 0, "2026-11-26")
    assert response.json()["total_minutes"] == 600
    assert len(response.json()["entries"]) == 1
    assert put(client, 0, "2026-11-24").status_code == 200
    assert db.scalar(select(func.count()).select_from(TimeEntry)) == 1


@pytest.mark.parametrize("day", ["2026-11-22", "2026-12-07", "2026-11-27"])
def test_invalid_date_does_not_create_timesheet(client, db, context, day):
    response = put(client, day=day)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_work_date"
    assert db.scalar(select(func.count()).select_from(Timesheet)) == 0


@pytest.mark.parametrize("minutes", [-1, 1441, 12.5])
def test_minutes_bounds_and_integer_validation(client, db, context, minutes):
    assert put(client, minutes).status_code == 422
    assert db.scalar(select(func.count()).select_from(TimeEntry)) == 0


def test_invalid_batch_is_atomic_and_duplicate_dates_rejected(client, db, context):
    put(client)
    response = client.put(
        "/api/me/timesheet/entries",
        json={
            "entries": [
                {"work_date": DAY, "minutes": 600},
                {"work_date": "2026-11-27", "minutes": 480},
            ]
        },
    )
    assert response.status_code == 422
    assert client.get("/api/me/timesheet").json()["total_minutes"] == 480
    response = client.put(
        "/api/me/timesheet/entries",
        json={"entries": [{"work_date": DAY, "minutes": 600}, {"work_date": DAY, "minutes": 300}]},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "duplicate_work_date"


def test_salaried_employee_cannot_log_hours(client, db, context, as_actor):
    company, *_ = context
    employee = f.make_employee(
        db, company, "Ana", "Reyes", pay_type=PayType.SALARY, amount_cents=6500000
    )
    as_actor(f.make_member(db, company, Role.EMPLOYEE, employee=employee))
    for response in (client.get("/api/me/timesheet"), put(client)):
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "not_hourly"


def test_staff_list_only_active_hourly_employees_and_requested_period(
    client, db, context, as_actor
):
    company, period, employee, _, manager, _ = context
    second = f.make_employee(db, company, "Bo", "Chen")
    f.make_employee(db, company, "Ana", "Reyes", pay_type=PayType.SALARY, amount_cents=6500000)
    gone = f.make_employee(db, company, "Sam", "Hale")
    gone.status = EmploymentStatus.TERMINATED
    f.make_employee(db, company, hire_date=period.end_date + timedelta(days=1))
    other, _ = f.other_company_setup(db)
    f.make_employee(db, other)
    db.flush()
    as_actor(manager)
    result = client.get(f"/api/timesheets?pay_period_id={period.id}")
    assert result.status_code == 200
    assert {row["employee_id"] for row in result.json()} == {str(employee.id), str(second.id)}
    assert db.scalar(select(func.count()).select_from(Timesheet)) == 2


def test_no_open_period(client, db, context, as_actor):
    company, period, _, _, manager, _ = context
    f.make_run(db, company, period=period, state=RunState.SUBMITTED)
    response = client.get("/api/me/timesheet")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "no_open_period"
    as_actor(manager)
    assert client.get("/api/timesheets").json() == []


def test_review_reject_edit_approve_flow(client, db, context, as_actor):
    _, period, employee, member, manager, _ = context
    data = put(client).json()
    sheet_id = data["id"]
    assert approved_minutes(db, employee.id, period.id) == 0
    as_actor(manager)
    response = client.post(f"/api/timesheets/{sheet_id}/approve", json={"note": " Checked "})
    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert response.json()["review_note"] == "Checked"
    assert response.json()["reviewed_at"].replace("+00:00", "Z") == "2026-11-26T18:00:00Z"
    assert response.json()["reviewed_by_name"] == db.get(User, manager.user_id).email
    assert approved_minutes(db, employee.id, period.id) == 480
    as_actor(member)
    assert put(client, 600).status_code == 409
    assert not client.get("/api/me/timesheet").json()["editable"]
    as_actor(manager)
    response = client.post(f"/api/timesheets/{sheet_id}/reject", json={"note": " Correct Tuesday "})
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert approved_minutes(db, employee.id, period.id) == 0
    as_actor(member)
    assert client.get("/api/me/timesheet").json()["editable"]
    edited = put(client, 600)
    assert edited.status_code == 200
    assert edited.json()["status"] == "open"
    assert edited.json()["review_note"] is None
    assert edited.json()["reviewed_at"] is None
    assert edited.json()["reviewed_by_name"] is None
    as_actor(manager)
    assert client.post(f"/api/timesheets/{sheet_id}/approve", json={}).status_code == 200
    audits = db.scalars(select(AuditLog).where(AuditLog.entity_id == sheet_id)).all()
    assert [entry.action for entry in audits].count(audit.TIMESHEET_APPROVED) == 2
    rejected = next(entry for entry in audits if entry.action == audit.TIMESHEET_REJECTED)
    assert rejected.before["status"] == "approved"
    assert rejected.after == {"status": "rejected", "review_note": "Correct Tuesday"}
    assert all(entry.actor_membership_id == manager.id for entry in audits)


@pytest.mark.parametrize("note", [None, "", "   "])
def test_rejection_requires_nonblank_note(client, db, context, as_actor, note):
    sheet_id = put(client).json()["id"]
    as_actor(context[4])
    response = client.post(f"/api/timesheets/{sheet_id}/reject", json={"note": note})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "note_required"
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 0


def test_rejected_can_be_approved_without_employee_edit(client, db, context, as_actor):
    sheet_id = put(client).json()["id"]
    as_actor(context[4])
    assert (
        client.post(f"/api/timesheets/{sheet_id}/reject", json={"note": "Check"}).status_code == 200
    )
    assert (
        client.post(f"/api/timesheets/{sheet_id}/reject", json={"note": "Again"}).status_code == 409
    )
    assert client.post(f"/api/timesheets/{sheet_id}/approve", json={}).status_code == 200
    assert client.post(f"/api/timesheets/{sheet_id}/approve", json={}).status_code == 409


@pytest.mark.parametrize("role,expected", [(Role.PAYROLL_MANAGER, 403), (Role.ADMIN, 200)])
def test_own_timesheet_approval(client, db, context, as_actor, role, expected):
    _, _, _, member, _, _ = context
    sheet_id = put(client).json()["id"]
    member.role = role
    db.flush()
    as_actor(member)
    response = client.post(f"/api/timesheets/{sheet_id}/approve", json={})
    assert response.status_code == expected
    if expected == 403:
        assert response.json()["detail"]["code"] == "own_timesheet"


def test_locked_sheet_is_read_only(client, db, context, as_actor):
    sheet_id = put(client).json()["id"]
    sheet = db.get(Timesheet, uuid.UUID(sheet_id))
    sheet.status = TimesheetStatus.LOCKED
    db.flush()
    response = put(client, 600)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "timesheet_locked"
    assert client.get("/api/me/timesheet").json()["editable"] is False
    as_actor(context[4])
    for action in ("approve", "reject"):
        response = client.post(f"/api/timesheets/{sheet_id}/{action}", json={"note": "Check"})
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "timesheet_locked"


def test_payroll_submission_locks_and_return_unlocks_hours(client, db, context, as_actor):
    _, period, employee, member, manager, _ = context
    sheet_id = put(client).json()["id"]
    as_actor(manager)
    client.post(f"/api/timesheets/{sheet_id}/approve", json={})
    run = client.post("/api/runs", json={"run_type": "regular", "pay_period_id": str(period.id)})
    assert run.status_code == 201
    run_id = run.json()["id"]
    assert run.json()["items"][0]["minutes"] == 480
    assert client.post(f"/api/runs/{run_id}/submit", json={}).status_code == 200
    listed = client.get(f"/api/timesheets?pay_period_id={period.id}").json()
    assert listed[0]["status"] == "locked" and not listed[0]["editable"]
    assert listed[0]["pay_period"]["regular_run_state"] == "submitted"
    assert approved_minutes(db, employee.id, period.id) == 480
    assert (
        client.post(f"/api/timesheets/{sheet_id}/reject", json={"note": "Change"}).status_code
        == 409
    )
    assert client.post(f"/api/runs/{run_id}/return-to-draft", json={}).status_code == 200
    assert (
        client.post(f"/api/timesheets/{sheet_id}/reject", json={"note": "Correct"}).status_code
        == 200
    )
    as_actor(member)
    assert put(client, 600).status_code == 200


@pytest.mark.parametrize("action", ["approve", "reject"])
@pytest.mark.parametrize("missing", [False, True])
def test_review_routes_hide_other_company_and_missing_sheets(
    client, db, context, as_actor, action, missing
):
    other, _ = f.other_company_setup(db)
    employee = f.make_employee(db, other)
    period = f.make_pay_period(db, other)
    sheet = Timesheet(company_id=other.id, employee_id=employee.id, pay_period_id=period.id)
    db.add(sheet)
    db.flush()
    as_actor(context[4])
    sheet_id = uuid.uuid4() if missing else sheet.id
    assert (
        client.post(f"/api/timesheets/{sheet_id}/{action}", json={"note": "Check"}).status_code
        == 404
    )


def test_foreign_period_filter_is_404(client, db, context, as_actor):
    other, _ = f.other_company_setup(db)
    period = f.make_pay_period(db, other)
    as_actor(context[4])
    assert client.get(f"/api/timesheets?pay_period_id={period.id}").status_code == 404


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("get", "/api/me/timesheet", None),
        ("put", "/api/me/timesheet/entries", {"entries": []}),
        ("get", "/api/timesheets", None),
        ("post", "/api/timesheets/{id}/approve", {}),
        ("post", "/api/timesheets/{id}/reject", {"note": "Check"}),
    ],
)
def test_no_session_is_401(client, method, path, body):
    path = path.replace("{id}", str(uuid.uuid4()))
    response = (
        client.request(method, path, json=body)
        if body is not None
        else client.request(method, path)
    )
    assert response.status_code == 401


def test_employee_cannot_review_and_former_cannot_use_timesheets(client, db, context, as_actor):
    sheet_id = put(client).json()["id"]
    assert client.get("/api/timesheets").status_code == 403
    assert client.post(f"/api/timesheets/{sheet_id}/approve", json={}).status_code == 403
    assert (
        client.post(f"/api/timesheets/{sheet_id}/reject", json={"note": "Check"}).status_code == 403
    )
    context[3].status = MembershipStatus.FORMER
    db.flush()
    as_actor(context[3])
    assert client.get("/api/me/timesheet").status_code == 403
    assert put(client).status_code == 403


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_review_and_audit_rollback_together(client, db, context, as_actor, monkeypatch, action):
    sheet_id = put(client).json()["id"]
    as_actor(context[4])

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
        raise RuntimeError("audit failed")

    app.dependency_overrides[get_db] = request_db
    monkeypatch.setattr(audit, "record", fail_record)
    with pytest.raises(RuntimeError, match="audit failed"):
        client.post(f"/api/timesheets/{sheet_id}/{action}", json={"note": "Check"})
    db.expire_all()
    assert db.get(Timesheet, uuid.UUID(sheet_id)).status == TimesheetStatus.OPEN
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 0


@pytest.fixture
def isolated_engine(engine):
    """Temporary schema for committed concurrency tests; shared test data stays untouched."""
    name = f"b07_concurrency_{uuid.uuid4().hex}"
    mapped = engine.execution_options(schema_translate_map={None: name})
    with engine.begin() as conn:
        conn.execute(CreateSchema(name))
    try:
        Base.metadata.create_all(mapped)
        yield mapped
    finally:
        with engine.begin() as conn:
            conn.execute(DropSchema(name, cascade=True))


def test_concurrent_lazy_get_creates_one_sheet(isolated_engine):
    with Session(isolated_engine) as session:
        company = f.make_company(session)
        f.make_pay_period(session, company)
        employee = f.make_employee(session, company, onboarded=False)
        actor = f.actor_for(
            session, f.make_member(session, company, Role.EMPLOYEE, employee=employee)
        )
        session.commit()
    barrier = Barrier(2)

    def fetch(_):
        barrier.wait(timeout=5)
        with Session(isolated_engine) as session:
            result = my_timesheet(actor=actor, db=session)
            session.commit()
            return result.id

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(fetch, [0, 1]))
    assert ids[0] == ids[1]
    with Session(isolated_engine) as session:
        assert session.scalar(select(func.count()).select_from(Timesheet)) == 1


def test_rejection_racing_submission_cannot_unlock_payroll_hours(isolated_engine):
    with Session(isolated_engine) as session:
        company = f.make_company(session)
        period = f.make_pay_period(session, company)
        employee = f.make_employee(session, company)
        manager = f.make_member(session, company, Role.PAYROLL_MANAGER)
        actor = f.actor_for(session, manager)
        sheet = Timesheet(
            company_id=company.id,
            employee_id=employee.id,
            pay_period_id=period.id,
            status=TimesheetStatus.APPROVED,
        )
        session.add(sheet)
        session.flush()
        run = f.make_run(session, company, period=period, employees=[employee])
        run_id, sheet_id, period_id = run.id, sheet.id, period.id
        session.commit()
    waiting = Event()

    def reject():
        with Session(isolated_engine) as session:
            conn = session.connection()

            def capture(conn, cursor, statement, *args):
                if (
                    "FROM" in statement
                    and "payroll_runs" in statement
                    and "FOR UPDATE" in statement
                ):
                    waiting.set()

            event.listen(conn, "before_cursor_execute", capture)
            try:
                reject_timesheet(sheet_id, ReviewIn(note="Correction"), actor=actor, db=session)
                session.commit()
                return "rejected"
            except AppError as exc:
                session.rollback()
                return exc.code
            finally:
                event.remove(conn, "before_cursor_execute", capture)

    with ThreadPoolExecutor(max_workers=1) as pool:
        with Session(isolated_engine) as session:
            transition(session, run_id, RunAction.SUBMIT, actor=actor)
            lock_for_period(session, period_id, actor)
            future = pool.submit(reject)
            try:
                assert waiting.wait(timeout=5)
            finally:
                session.commit()  # Always release locks before waiting for the other transaction.
        assert future.result(timeout=5) == "timesheet_locked"
    with Session(isolated_engine) as session:
        assert session.get(Timesheet, sheet_id).status == TimesheetStatus.LOCKED
        assert session.get(PayrollRun, run_id).state == RunState.SUBMITTED


def test_other_period_is_not_marked_editable_for_staff_on_payroll(client, db, context, as_actor):
    company, _, _, member, _, _ = context
    member.role = Role.ADMIN
    db.flush()
    as_actor(member)
    future = f.make_pay_period(db, company, date(2027, 1, 8))
    response = client.get(f"/api/timesheets?pay_period_id={future.id}")
    assert response.status_code == 200
    assert response.json()[0]["editable"] is False
    assert client.get("/api/me/timesheet").json()["editable"] is True
