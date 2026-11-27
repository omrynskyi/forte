"""B-04: invitations, role permissions, tenant isolation and concurrent last-Admin protection."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema, DropSchema

from app import audit, clock
from app.auth.tokens import hash_token
from app.config import get_settings
from app.db import get_db
from app.errors import AppError
from app.main import app
from app.models import (
    AuditLog,
    AuthSession,
    Company,
    Employee,
    MagicLinkToken,
    Membership,
    Notification,
    User,
)
from app.models.base import Base
from app.models.enums import MembershipStatus, Role
from app.routers.members import change_role, invite_member, remove_member
from app.schemas.members import InviteIn, RoleChangeIn
from tests import factories as f

NOW = datetime(2026, 11, 26, 18, tzinfo=UTC)
INVITE = {"email": "ana-team@larkspur.example", "role": "payroll_manager"}


@pytest.fixture(autouse=True)
def frozen(monkeypatch):
    monkeypatch.setattr(clock, "now", lambda: NOW)


@pytest.fixture
def admin_context(db, as_actor):
    company = f.make_company(db)
    admin = f.make_member(db, company)
    as_actor(admin)
    return company, admin


def set_cookie(db, client, member):
    raw = uuid.uuid4().hex
    db.add(
        AuthSession(
            user_id=member.user_id, token_hash=hash_token(raw), expires_at=NOW + timedelta(hours=12)
        )
    )
    db.flush()
    client.cookies.set(get_settings().session_cookie_name, raw)


@pytest.mark.parametrize("role", ["admin", "payroll_manager"])
def test_admin_invites_staff_and_invite_can_be_redeemed(client, db, outbox, admin_context, role):
    company, admin = admin_context
    response = client.post("/api/members/invite", json={**INVITE, "role": role})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == INVITE["email"]
    assert body["role"] == role
    assert body["status"] == "invited"
    assert body["employee_id"] is None
    assert body["display_name"] is None
    assert response.headers["cache-control"] == "no-store"
    member = db.get(Membership, uuid.UUID(body["id"]))
    assert member.company_id == company.id
    assert member.invited_by_membership_id == admin.id
    assert len(outbox.outbox) == 1
    to, subject, message = outbox.outbox[0]
    assert to == INVITE["email"]
    assert "invitation" in subject.lower()
    notification = db.scalars(
        select(Notification).where(Notification.user_id == member.user_id)
    ).one()
    assert notification.kind == "invite"
    assert notification.company_id == company.id
    entry = db.scalars(select(AuditLog).where(AuditLog.action == audit.MEMBER_INVITED)).one()
    assert entry.actor_membership_id == admin.id
    assert entry.after["role"] == role
    assert entry.company_id == company.id
    token = parse_qs(urlparse(message.split("Sign in to Forte: ")[1].split()[0]).query)["token"][0]
    assert token not in str(entry.after)
    response = client.post("/api/auth/verify", json={"token": token})
    assert response.status_code == 200
    assert response.json()["membership"]["role"] == role
    assert response.json()["membership"]["status"] == "active"


def test_existing_unassigned_user_reused_and_email_normalized(client, db, admin_context):
    user = f.make_user(db, INVITE["email"])
    response = client.post("/api/members/invite", json={**INVITE, "email": INVITE["email"].upper()})
    assert response.status_code == 201
    member = db.get(Membership, uuid.UUID(response.json()["id"]))
    assert member.user_id == user.id
    assert response.json()["email"] == user.email
    assert db.scalar(select(func.count()).select_from(User).where(User.email == user.email)) == 1


@pytest.mark.parametrize("foreign", [False, True])
@pytest.mark.parametrize(
    "status", [MembershipStatus.ACTIVE, MembershipStatus.INVITED, MembershipStatus.REMOVED]
)
def test_existing_membership_is_not_reassigned_or_reactivated(
    client, db, admin_context, foreign, status
):
    company, _ = admin_context
    if foreign:
        company, _ = f.other_company_setup(db)
    member = f.make_member(db, company, Role.ADMIN, email=INVITE["email"], status=status)
    response = client.post("/api/members/invite", json=INVITE)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "email_in_use"
    db.refresh(member)
    assert member.role == Role.ADMIN
    assert member.status == status
    assert db.scalar(select(func.count()).select_from(MagicLinkToken)) == 0
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 0


def test_member_list_scoped_and_names_when_on_payroll(client, db, admin_context, as_actor):
    company, admin = admin_context
    employee = f.make_employee(db, company)
    manager = f.make_member(db, company, Role.PAYROLL_MANAGER, employee=employee)
    removed = f.make_member(db, company, status=MembershipStatus.REMOVED)
    other, other_admin = f.other_company_setup(db)
    response = client.get("/api/members")
    assert response.status_code == 200
    members = {item["id"]: item for item in response.json()}
    assert set(members) == {str(admin.id), str(manager.id), str(removed.id)}
    assert str(other_admin.id) not in members
    assert members[str(manager.id)]["display_name"] == "Devon Park"
    assert members[str(manager.id)]["employee_id"] == str(employee.id)
    assert members[str(removed.id)]["status"] == "removed"
    as_actor(manager)
    assert client.get("/api/members").status_code == 200
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 0


@pytest.mark.parametrize(
    "role,status",
    [
        (Role.PAYROLL_MANAGER, MembershipStatus.ACTIVE),
        (Role.EMPLOYEE, MembershipStatus.ACTIVE),
        (Role.ADMIN, MembershipStatus.FORMER),
    ],
)
def test_mutations_require_active_admin(client, db, as_actor, role, status):
    company = f.make_company(db)
    caller = f.make_member(db, company, role, status=status)
    target = f.make_member(db, company)
    as_actor(caller)
    assert client.post("/api/members/invite", json=INVITE).status_code == 403
    assert client.patch(f"/api/members/{target.id}", json={"role": "employee"}).status_code == 403
    assert client.delete(f"/api/members/{target.id}").status_code == 403
    if role != Role.PAYROLL_MANAGER or status != MembershipStatus.ACTIVE:
        assert client.get("/api/members").status_code == 403


@pytest.mark.parametrize("method", ["patch", "delete"])
@pytest.mark.parametrize(
    "other_status",
    [None, MembershipStatus.INVITED, MembershipStatus.FORMER, MembershipStatus.REMOVED],
)
def test_last_active_admin_cannot_be_demoted_or_removed(
    client, db, admin_context, method, other_status
):
    company, admin = admin_context
    if other_status:
        f.make_member(db, company, Role.ADMIN, status=other_status)
    response = (
        client.patch(f"/api/members/{admin.id}", json={"role": "payroll_manager"})
        if method == "patch"
        else client.delete(f"/api/members/{admin.id}")
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "last_admin"
    db.refresh(admin)
    assert admin.role == Role.ADMIN and admin.status == MembershipStatus.ACTIVE
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 0


def test_cannot_change_own_role_even_with_another_admin(client, db, admin_context):
    company, admin = admin_context
    f.make_member(db, company)
    response = client.patch(f"/api/members/{admin.id}", json={"role": "employee"})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "own_role"
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 0


def test_change_role_and_remove_are_audited(client, db, admin_context):
    company, admin = admin_context
    target = f.make_member(db, company, Role.ADMIN)
    response = client.patch(f"/api/members/{target.id}", json={"role": "payroll_manager"})
    assert response.status_code == 200
    assert response.json()["role"] == "payroll_manager"
    changed = db.scalars(select(AuditLog).where(AuditLog.action == audit.MEMBER_ROLE_CHANGED)).one()
    assert changed.before == {"role": "admin"}
    assert changed.after == {"role": "payroll_manager"}
    assert changed.actor_membership_id == admin.id
    response = client.delete(f"/api/members/{target.id}")
    assert response.status_code == 204 and response.content == b""
    db.refresh(target)
    assert target.status == MembershipStatus.REMOVED
    removed = db.scalars(select(AuditLog).where(AuditLog.action == audit.MEMBER_REMOVED)).one()
    assert removed.before["status"] == "active"
    assert removed.after["status"] == "removed"
    assert removed.company_id == company.id
    assert client.delete(f"/api/members/{target.id}").status_code == 204
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == audit.MEMBER_REMOVED)
        )
        == 1
    )
    assert client.patch(f"/api/members/{target.id}", json={"role": "admin"}).status_code == 409


def test_role_change_does_not_activate_invited_admin(client, db, admin_context):
    company, _ = admin_context
    invited = f.make_member(db, company, Role.PAYROLL_MANAGER, status=MembershipStatus.INVITED)
    response = client.patch(f"/api/members/{invited.id}", json={"role": "admin"})
    assert response.status_code == 200
    assert response.json()["role"] == "admin"
    assert response.json()["status"] == "invited"


def test_former_document_access_preserved(client, db, admin_context):
    company, _ = admin_context
    former = f.make_member(db, company, Role.EMPLOYEE, status=MembershipStatus.FORMER)
    response = client.delete(f"/api/members/{former.id}")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "former_member"
    db.refresh(former)
    assert former.status == MembershipStatus.FORMER


def test_removed_member_loses_access_with_real_cookie(client, db):
    company = f.make_company(db)
    admin = f.make_member(db, company)
    target = f.make_member(db, company, Role.PAYROLL_MANAGER)
    set_cookie(db, client, target)
    assert client.get("/api/members").status_code == 200
    # Change to an Admin cookie for removal; retain the original raw token for replay.
    target_cookie = client.cookies[get_settings().session_cookie_name]
    set_cookie(db, client, admin)
    assert client.delete(f"/api/members/{target.id}").status_code == 204
    client.cookies.set(get_settings().session_cookie_name, target_cookie)
    assert client.get("/api/members").status_code == 403
    assert client.get("/api/auth/me").status_code == 403


@pytest.mark.parametrize("method", ["patch", "delete"])
@pytest.mark.parametrize("missing", [False, True])
def test_membership_ids_are_company_scoped(client, db, admin_context, method, missing):
    _, foreign_admin = f.other_company_setup(db)
    target_id = uuid.uuid4() if missing else foreign_admin.id
    response = (
        client.patch(f"/api/members/{target_id}", json={"role": "employee"})
        if method == "patch"
        else client.delete(f"/api/members/{target_id}")
    )
    assert response.status_code == 404
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 0


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("get", "/api/members", None),
        ("post", "/api/members/invite", INVITE),
        ("patch", "/api/members/{id}", {"role": "employee"}),
        ("delete", "/api/members/{id}", None),
    ],
)
def test_unauthenticated_requests(client, method, path, body):
    path = path.replace("{id}", str(uuid.uuid4()))
    response = client.request(method, path, json=body) if body else client.request(method, path)
    assert response.status_code == 401


def test_employee_invites_and_invalid_roles_rejected(client, db, admin_context):
    assert (
        client.post("/api/members/invite", json={**INVITE, "role": "employee"}).status_code == 422
    )
    assert (
        client.post("/api/members/invite", json={**INVITE, "email": "invalid"}).status_code == 422
    )
    assert (
        client.patch(f"/api/members/{admin_context[1].id}", json={"role": "root"}).status_code
        == 422
    )


@pytest.mark.parametrize("action", ["invite", "role", "remove"])
def test_stale_admin_actor_cannot_mutate(client, db, admin_context, action):
    company, admin = admin_context
    actor = f.actor_for(db, admin)
    admin.role = Role.PAYROLL_MANAGER
    target = f.make_member(db, company, Role.EMPLOYEE)
    db.flush()
    with pytest.raises(AppError) as err:
        if action == "invite":
            invite_member(InviteIn(**INVITE), actor=actor, db=db, email=None)
        elif action == "role":
            change_role(target.id, RoleChangeIn(role="admin"), actor=actor, db=db)
        else:
            remove_member(target.id, actor=actor, db=db)
    assert err.value.status_code == 403
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 0


@pytest.mark.parametrize("action", ["invite", "role", "remove"])
def test_failed_operation_rolls_back_membership_and_audit(
    client, db, admin_context, outbox, monkeypatch, action
):
    company, admin = admin_context
    target = f.make_member(db, company, Role.PAYROLL_MANAGER)

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

    app.dependency_overrides[get_db] = request_db

    def fail(*args, **kwargs):
        raise RuntimeError("operation failed")

    if action == "invite":
        monkeypatch.setattr(outbox, "send", fail)
    else:
        original = audit.record

        def fail_after_record(*args, **kwargs):
            original(*args, **kwargs)
            fail()

        monkeypatch.setattr(audit, "record", fail_after_record)
    with pytest.raises(RuntimeError, match="operation failed"):
        if action == "invite":
            client.post("/api/members/invite", json=INVITE)
        elif action == "role":
            client.patch(f"/api/members/{target.id}", json={"role": "admin"})
        else:
            client.delete(f"/api/members/{target.id}")
    db.expire_all()
    assert target.status == MembershipStatus.ACTIVE and target.role == Role.PAYROLL_MANAGER
    assert db.scalar(select(func.count()).select_from(Membership)) == 2
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 0
    assert db.scalar(select(func.count()).select_from(MagicLinkToken)) == 0
    assert db.scalar(select(func.count()).select_from(Notification)) == 0


@pytest.mark.parametrize(
    "action,expected_error", [("remove_self", "last_admin"), ("demote_other", "forbidden")]
)
def test_concurrent_admin_changes_keep_one_active_admin(engine, action, expected_error):
    """Race real committed transactions in an isolated schema, then drop only that schema.

    Isolated tables avoid leaving committed fake users or immutable audit rows in the
    shared test database. This tests application locking, not migration triggers.
    """
    schema = f"b04_concurrency_{uuid.uuid4().hex}"
    scoped_engine = engine.execution_options(schema_translate_map={None: schema})
    tables = [
        Company.__table__,
        User.__table__,
        Employee.__table__,
        Membership.__table__,
        AuditLog.__table__,
    ]
    with engine.begin() as conn:
        conn.execute(CreateSchema(schema))
    try:
        Base.metadata.create_all(scoped_engine, tables=tables)
        with Session(scoped_engine) as session:
            company = f.make_company(session)
            admins = [f.make_member(session, company), f.make_member(session, company)]
            actors = [f.actor_for(session, member) for member in admins]
            company_id = company.id
            session.commit()
        barrier = Barrier(2)

        def mutate(index):
            barrier.wait(timeout=5)
            actor = actors[index]
            with Session(scoped_engine) as session:
                try:
                    if action == "remove_self":
                        remove_member(actor.membership_id, actor=actor, db=session)
                    else:
                        change_role(
                            actors[1 - index].membership_id,
                            RoleChangeIn(role="payroll_manager"),
                            actor=actor,
                            db=session,
                        )
                    session.commit()
                    return "ok"
                except AppError as exc:
                    session.rollback()
                    return exc.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(mutate, [0, 1]))
        assert sorted(results) == sorted(["ok", expected_error])
        with Session(scoped_engine) as session:
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(Membership)
                    .where(
                        Membership.company_id == company_id,
                        Membership.role == Role.ADMIN,
                        Membership.status == MembershipStatus.ACTIVE,
                    )
                )
                == 1
            )
            assert session.scalar(select(func.count()).select_from(AuditLog)) == 1
    finally:
        with engine.begin() as conn:
            conn.execute(DropSchema(schema, cascade=True))
