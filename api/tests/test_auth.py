"""B-01: magic links, session cookies, invitation activation and development guards.

B-02 still owns get_session_user. /me tests override that dependency explicitly rather
than installing authentication into protected endpoints as part of this issue.
"""

import secrets
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app import audit, clock
from app.auth.deps import SessionUser, get_session_user
from app.auth.tokens import consume_magic_link, hash_token, issue_magic_link
from app.config import Settings, get_settings
from app.db import get_db
from app.errors import Unauthorized
from app.main import app
from app.models import AuditLog, AuthSession, MagicLinkToken, Notification, User
from app.models.enums import MagicLinkPurpose, MembershipStatus, Role
from tests import factories as f

NOW = datetime(2026, 11, 24, 18, tzinfo=UTC)


@pytest.fixture(autouse=True)
def frozen(monkeypatch):
    monkeypatch.setattr(clock, "now", lambda: NOW)


def request_link(client, outbox, email):
    response = client.post("/api/auth/magic-link", json={"email": email})
    assert response.status_code == 202, response.text
    text = outbox.outbox[-1][2]
    url = text.split("Sign in to Forte: ", 1)[1].split()[0]
    return parse_qs(urlparse(url).query)["token"][0]


def test_new_signup_full_flow(client, db, outbox):
    token = request_link(client, outbox, "NEW@larkspur.example")
    user = db.scalars(select(User).where(User.email == "new@larkspur.example")).one()
    link = db.scalars(select(MagicLinkToken).where(MagicLinkToken.user_id == user.id)).one()
    assert link.token_hash == hash_token(token)
    assert link.token_hash != token
    assert link.expires_at == NOW + timedelta(minutes=15)
    assert link.purpose == MagicLinkPurpose.LOGIN
    assert link.used_at is None
    assert len(token) == 43
    to, subject, body = outbox.outbox[-1]
    assert to == user.email
    assert "works once, for 15 minutes" in body
    assert f"{get_settings().web_base_url}/auth/verify?token=" in body
    notification = db.scalars(select(Notification).where(Notification.user_id == user.id)).one()
    assert notification.kind == "magic_link"
    assert notification.subject == subject
    assert notification.sent_at == NOW
    assert notification.company_id is None

    response = client.post("/api/auth/verify", json={"token": token})
    assert response.status_code == 200, response.text
    info = response.json()
    assert info["user_id"] == str(user.id)
    assert info["membership"] is None
    assert info["company"] is None
    assert info["employee_id"] is None
    assert info["onboarding"] is None
    cookie = response.cookies[get_settings().session_cookie_name]
    session = db.scalars(select(AuthSession).where(AuthSession.user_id == user.id)).one()
    assert session.token_hash == hash_token(cookie)
    assert cookie != token
    assert session.expires_at == NOW + timedelta(hours=12)
    assert session.revoked_at is None
    assert session.user_agent
    db.refresh(user)
    db.refresh(link)
    assert user.last_login_at == link.used_at == NOW
    header = response.headers["set-cookie"]
    assert "HttpOnly" in header
    assert "SameSite=lax" in header
    assert "Max-Age=43200" in header
    assert "Path=/" in header
    assert "Domain=" not in header
    assert "Secure" not in header
    assert response.headers["cache-control"] == "no-store"
    entry = db.scalars(select(AuditLog).where(AuditLog.action == audit.USER_SIGNED_IN)).one()
    assert entry.actor_user_id == user.id
    assert entry.company_id is None
    assert token not in str(entry.after) and cookie not in str(entry.after)

    replay = client.post("/api/auth/verify", json={"token": token})
    assert replay.status_code == 401
    assert replay.json()["detail"]["code"] == "link_used"
    assert "set-cookie" not in replay.headers
    assert db.scalar(select(func.count()).select_from(AuthSession)) == 1


def test_known_unknown_response_and_case_normalization(client, db, outbox):
    user = f.make_user(db, "known@larkspur.example")
    known = client.post("/api/auth/magic-link", json={"email": "KNOWN@larkspur.example"})
    unknown = client.post("/api/auth/magic-link", json={"email": "unknown@larkspur.example"})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert db.scalar(select(func.count()).select_from(User)) == 2
    assert (
        db.scalar(select(MagicLinkToken.user_id).where(MagicLinkToken.user_id == user.id))
        == user.id
    )


@pytest.mark.parametrize("raw", ["", "not-a-real-link", "x" * 1000])
def test_invalid_tokens(client, raw):
    response = client.post("/api/auth/verify", json={"token": raw})
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "link_invalid"
    assert "set-cookie" not in response.headers


def test_expiry_at_boundary(client, db, outbox, monkeypatch):
    token = request_link(client, outbox, "expired@larkspur.example")
    monkeypatch.setattr(clock, "now", lambda: NOW + timedelta(minutes=15))
    response = client.post("/api/auth/verify", json={"token": token})
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "link_expired"
    assert db.scalar(select(func.count()).select_from(AuthSession)) == 0
    assert db.scalar(select(MagicLinkToken.used_at)) is None


@pytest.mark.parametrize("onboarded", [True, False])
def test_invite_activation_and_me(client, db, outbox, onboarded):
    company = f.make_company(db)
    employee = f.make_employee(db, company, onboarded=onboarded)
    member = f.make_member(
        db, company, Role.EMPLOYEE, employee=employee, status=MembershipStatus.INVITED
    )
    user = db.get(User, member.user_id)
    issue_magic_link(db, user, MagicLinkPurpose.INVITE, outbox)
    token = parse_qs(urlparse(outbox.outbox[-1][2].split()[4]).query)["token"][0]
    response = client.post("/api/auth/verify", json={"token": token})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["display_name"] == "Devon Park"
    assert data["membership"] == {"id": str(member.id), "role": "employee", "status": "active"}
    assert data["company"]["id"] == str(company.id)
    assert data["company"]["setup_complete"] is False
    assert data["employee_id"] == str(employee.id)
    assert data["onboarding"]["complete"] is onboarded
    db.refresh(member)
    assert member.status == MembershipStatus.ACTIVE
    notification = db.scalars(select(Notification).where(Notification.user_id == user.id)).one()
    assert notification.company_id == company.id
    assert notification.kind == "invite"
    entry = db.scalars(select(AuditLog).where(AuditLog.action == audit.USER_SIGNED_IN)).one()
    assert entry.actor_membership_id == member.id
    assert entry.company_id == company.id
    assert entry.before == {"membership_status": "invited"}
    assert entry.after == {"membership_status": "active"}
    app.dependency_overrides[get_session_user] = lambda: SessionUser(user.id, user.email)
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json() == data
    assert me.headers["cache-control"] == "no-store"


def test_me_without_membership(client, db):
    user = f.make_user(db)
    app.dependency_overrides[get_session_user] = lambda: SessionUser(user.id, user.email)
    response = client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json()["membership"] is None
    assert response.json()["onboarding"] is None
    assert response.json()["company"] is None


def test_me_respects_b02_dependency(client):
    assert client.get("/api/auth/me").status_code == 401


@pytest.mark.parametrize(
    "status", [MembershipStatus.ACTIVE, MembershipStatus.FORMER, MembershipStatus.REMOVED]
)
def test_existing_membership_status_preserved(client, db, outbox, status):
    company = f.make_company(db)
    member = f.make_member(db, company, status=status)
    user = db.get(User, member.user_id)
    token = request_link(client, outbox, user.email)
    response = client.post("/api/auth/verify", json={"token": token})
    db.refresh(member)
    assert member.status == status
    if status == MembershipStatus.REMOVED:
        assert response.status_code == 403
        assert "set-cookie" not in response.headers
        assert db.scalar(select(func.count()).select_from(AuthSession)) == 0
    else:
        assert response.status_code == 200
        assert response.json()["membership"]["status"] == status.value


def test_logout_revokes_only_current_session(client, db, outbox):
    token = request_link(client, outbox, "logout@larkspur.example")
    first = client.post("/api/auth/verify", json={"token": token}).cookies[
        get_settings().session_cookie_name
    ]
    token = request_link(client, outbox, "logout@larkspur.example")
    second = client.post("/api/auth/verify", json={"token": token}).cookies[
        get_settings().session_cookie_name
    ]
    assert first != second
    response = client.post("/api/auth/logout")
    assert response.status_code == 204
    assert response.content == b""
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert get_settings().session_cookie_name not in client.cookies
    current = db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(second)))
    other = db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(first)))
    assert current.revoked_at == NOW
    assert other.revoked_at is None
    assert client.post("/api/auth/logout").status_code == 204


def test_unknown_logout_cookie(client):
    client.cookies.set(get_settings().session_cookie_name, "unknown")
    assert client.post("/api/auth/logout").status_code == 204


def test_secure_cookie_and_session_settings(client, db, outbox, monkeypatch):
    settings = get_settings().model_copy(
        update={"session_cookie_secure": True, "session_ttl_hours": 2}
    )
    monkeypatch.setattr("app.auth.sessions.get_settings", lambda: settings)
    token = request_link(client, outbox, "secure@larkspur.example")
    response = client.post("/api/auth/verify", json={"token": token})
    assert "Secure" in response.headers["set-cookie"]
    assert "Max-Age=7200" in response.headers["set-cookie"]
    assert db.scalar(select(AuthSession.expires_at)) == NOW + timedelta(hours=2)
    logout = client.post("/api/auth/logout")
    assert "Secure" in logout.headers["set-cookie"]


@pytest.mark.parametrize("prod,enabled", [(False, False), (True, False), (True, True)])
def test_dev_routes_disabled(client, monkeypatch, prod, enabled):
    # model_copy deliberately bypasses startup validation to test the runtime prod check too.
    settings = get_settings().model_copy(
        update={"env": "prod" if prod else "test", "dev_login_enabled": enabled}
    )
    monkeypatch.setattr("app.routers.auth.get_settings", lambda: settings)
    assert client.get("/api/auth/dev/users").status_code == 404
    assert (
        client.post("/api/auth/dev/login", json={"email": "any@larkspur.example"}).status_code
        == 404
    )


def test_prod_settings_guard_dev_login():
    with pytest.raises(ValueError, match="DEV_LOGIN_ENABLED"):
        Settings(
            _env_file=None,
            env="prod",
            encryption_key="non-default",
            session_cookie_secure=True,
            dev_login_enabled=True,
            storage_backend="s3",
        )


def test_dev_switcher(client, db):
    company = f.make_company(db)
    employee = f.make_employee(db, company)
    member = f.make_member(db, company, Role.EMPLOYEE, employee=employee)
    f.make_member(db, company, status=MembershipStatus.REMOVED)
    user = db.get(User, member.user_id)
    response = client.get("/api/auth/dev/users")
    assert response.status_code == 200
    assert response.json() == [
        {"email": user.email, "display_name": "Devon Park", "role": "employee", "status": "active"}
    ]
    response = client.post("/api/auth/dev/login", json={"email": user.email.upper()})
    assert response.status_code == 200
    assert response.json()["employee_id"] == str(employee.id)
    assert get_settings().session_cookie_name in response.cookies
    assert db.scalar(select(func.count()).select_from(AuthSession)) == 1
    assert db.scalar(select(func.count()).select_from(MagicLinkToken)) == 0
    assert (
        client.post("/api/auth/dev/login", json={"email": "unknown@larkspur.example"}).status_code
        == 404
    )


def test_dev_login_rejects_removed_member(client, db):
    company = f.make_company(db)
    member = f.make_member(db, company, status=MembershipStatus.REMOVED)
    user = db.get(User, member.user_id)
    response = client.post("/api/auth/dev/login", json={"email": user.email})
    assert response.status_code == 403
    assert "set-cookie" not in response.headers


def test_concurrent_token_consumption(engine):
    """Two real transactions race for one committed token; only one may consume it.

    Dedicated rows are removed afterwards; this test doesn't create immutable audit rows.
    """
    raw = secrets.token_urlsafe(32)
    user_id = uuid.uuid4()
    with Session(engine) as session:
        session.add(User(id=user_id, email=f"concurrent-{user_id}@larkspur.example"))
        session.flush()
        session.add(
            MagicLinkToken(
                user_id=user_id,
                token_hash=hash_token(raw),
                purpose=MagicLinkPurpose.LOGIN,
                expires_at=NOW + timedelta(minutes=15),
            )
        )
        session.commit()

    barrier = Barrier(2)

    def consume():
        barrier.wait(timeout=5)
        with Session(engine) as session:
            try:
                consume_magic_link(session, raw)
                session.commit()
                return "success"
            except Unauthorized as exc:
                session.rollback()
                return exc.code

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: consume(), range(2)))
        assert sorted(results) == ["link_used", "success"]
    finally:
        with Session(engine) as session:
            session.execute(delete(MagicLinkToken).where(MagicLinkToken.user_id == user_id))
            session.execute(delete(User).where(User.id == user_id))
            session.commit()


@pytest.fixture
def transactional_requests(client, db):
    """Exercise get_db's commit/rollback contract within the fixture's outer transaction."""

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
    return client


def test_verify_failure_rolls_back_token_session_and_activation(
    transactional_requests, db, outbox, monkeypatch
):
    client = transactional_requests
    company = f.make_company(db)
    member = f.make_member(db, company, status=MembershipStatus.INVITED)
    user = db.get(User, member.user_id)
    token = request_link(client, outbox, user.email)

    def fail_response(*args):
        raise RuntimeError("response construction failed")

    with monkeypatch.context() as patch:
        patch.setattr("app.routers.auth.build_me", fail_response)
        with pytest.raises(RuntimeError, match="response construction failed"):
            client.post("/api/auth/verify", json={"token": token})
    db.expire_all()
    assert (
        db.scalar(select(MagicLinkToken.used_at).where(MagicLinkToken.user_id == user.id)) is None
    )
    assert db.scalar(select(func.count()).select_from(AuthSession)) == 0
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 0
    assert member.status == MembershipStatus.INVITED
    assert user.last_login_at is None
    assert client.post("/api/auth/verify", json={"token": token}).status_code == 200


def test_email_failure_rolls_back_signup_and_token(transactional_requests, db, outbox, monkeypatch):
    def fail_send(*args):
        raise RuntimeError("mail unavailable")

    monkeypatch.setattr(outbox, "send", fail_send)
    with pytest.raises(RuntimeError, match="mail unavailable"):
        transactional_requests.post(
            "/api/auth/magic-link", json={"email": "failed@larkspur.example"}
        )
    assert db.scalar(select(User).where(User.email == "failed@larkspur.example")) is None
    assert db.scalar(select(func.count()).select_from(MagicLinkToken)) == 0
    assert db.scalar(select(func.count()).select_from(Notification)) == 0
