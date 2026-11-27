"""Audit log API and plain-language summaries (B-08, AUD-1, AUD-2)."""

import uuid
from types import SimpleNamespace

import pytest

from app import audit
from app.models import AuditLog
from app.models.enums import Role
from app.services.audit_text import summarize
from tests import factories as f

ACTIONS = {v for k, v in vars(audit).items() if k.isupper() and isinstance(v, str) and "." in v}


def _entry(name: str, **after) -> SimpleNamespace:
    return SimpleNamespace(action=name, before=None, after=after or None)


@pytest.mark.parametrize("action", sorted(ACTIONS))
def test_every_constant_renders(action):
    for names in ({}, {"actor": "Ana Lindqvist", "entity": "Devon Park", "pay_date": "Dec 11"}):
        s = summarize(_entry(action), names)
        assert s.endswith(".") and len(s) > 10


def test_known_sentences_and_unknown_fallback():
    names = {"actor": "Ana Lindqvist", "pay_date": "Dec 11"}
    e = _entry(audit.RUN_TRANSITIONED, state="submitted", action="submit")
    assert summarize(e, names) == "Ana Lindqvist submitted payroll for Dec 11."
    assert summarize(_entry("widget.exploded"), {"actor": "Ana"}) == (
        "Ana made a change (widget exploded)."
    )
    assert summarize(_entry(audit.USER_SIGNED_IN), {}) == "Forte signed in."


def _log(db, company, member, action, entity_type="employee", entity_id=None, **kw):
    entry = AuditLog(
        company_id=company.id,
        actor_user_id=member.user_id if member else None,
        actor_membership_id=member.id if member else None,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id or uuid.uuid4()),
        **kw,
    )
    db.add(entry)
    db.flush()
    return entry


def test_admin_sees_all_with_names(client, db, as_actor):
    co = f.make_company(db)
    emp = f.make_employee(db, co, "Ana", "Lindqvist")
    admin = f.make_member(db, co, Role.ADMIN, employee=emp)
    pm = f.make_member(db, co, Role.PAYROLL_MANAGER, email="pm@larkspur.example")
    run = f.make_run(db, co, employees=[emp])
    _log(db, co, admin, audit.EMPLOYEE_CREATED, entity_id=emp.id)
    _log(
        db,
        co,
        pm,
        audit.RUN_TRANSITIONED,
        "payroll_run",
        run.id,
        after={"state": "submitted", "action": "submit"},
    )
    _log(db, co, None, audit.USER_SIGNED_IN, "user")
    as_actor(admin)
    r = client.get("/api/audit")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 3
    summaries = [x["summary"] for x in rows]
    assert "Ana Lindqvist added Ana Lindqvist as an employee." in summaries
    assert any(s.startswith("pm@larkspur.example submitted payroll for ") for s in summaries)
    assert rows[0]["actor_name"] is None  # newest first: the system entry
    assert {x["actor_role"] for x in rows} == {None, "admin", "payroll_manager"}


def test_pm_sees_only_own_actions(client, db, as_actor):
    co = f.make_company(db)
    admin = f.make_member(db, co, Role.ADMIN)
    pm = f.make_member(db, co, Role.PAYROLL_MANAGER)
    _log(db, co, admin, audit.COMPANY_UPDATED, "company")
    mine = _log(db, co, pm, audit.PAY_SCHEDULE_SET, "company")
    as_actor(pm)
    rows = client.get("/api/audit").json()
    assert [x["id"] for x in rows] == [mine.id]


def test_filters_and_limit(client, db, as_actor):
    co = f.make_company(db)
    admin = f.make_member(db, co, Role.ADMIN)
    eid = uuid.uuid4()
    for _ in range(3):
        _log(db, co, admin, audit.COMPENSATION_SET, entity_id=eid)
    _log(db, co, admin, audit.COMPANY_UPDATED, "company")
    as_actor(admin)
    assert len(client.get("/api/audit", params={"action": audit.COMPENSATION_SET}).json()) == 3
    assert len(client.get("/api/audit", params={"entity_type": "company"}).json()) == 1
    assert len(client.get("/api/audit", params={"entity_id": str(eid)}).json()) == 3
    assert len(client.get("/api/audit", params={"limit": 2}).json()) == 2
    assert client.get("/api/audit", params={"limit": 501}).status_code == 422


def test_cross_tenant_isolation(client, db, as_actor):
    co = f.make_company(db)
    admin = f.make_member(db, co, Role.ADMIN)
    other, other_admin = f.other_company_setup(db)
    _log(db, other, other_admin, audit.COMPANY_UPDATED, "company")
    mine = _log(db, co, admin, audit.COMPANY_UPDATED, "company")
    as_actor(admin)
    assert [x["id"] for x in client.get("/api/audit").json()] == [mine.id]


def test_employee_forbidden_and_no_write_routes(client, db, as_actor):
    co = f.make_company(db)
    emp = f.make_employee(db, co)
    member = f.make_member(db, co, Role.EMPLOYEE, employee=emp)
    as_actor(member)
    assert client.get("/api/audit").status_code == 403
    admin = f.make_member(db, co, Role.ADMIN)
    as_actor(admin)
    for method in ("post", "put", "patch", "delete"):
        assert getattr(client, method)("/api/audit").status_code == 405
