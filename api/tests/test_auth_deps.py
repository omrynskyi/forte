"""B-02: real cookie authentication, current membership, tenant isolation and query budget.

No authentication dependencies are overridden. A-06/B-06 routes may still return their
501 task placeholders after successful authentication; the auth guards must run first.
"""

import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import event, update
from starlette.requests import Request

from app import clock
from app.auth.deps import get_actor, get_session_user
from app.auth.tokens import hash_token
from app.config import get_settings
from app.models import AuthSession, Membership, User
from app.models.enums import MembershipStatus, Role
from tests import factories as f

NOW = datetime(2026, 11, 25, 18, tzinfo=UTC)


@pytest.fixture(autouse=True)
def frozen(monkeypatch):
    monkeypatch.setattr(clock, "now", lambda: NOW)


def session_cookie(db, client, user_id, *, expires_at=None, revoked_at=None):
    raw = secrets.token_urlsafe(32)
    session = AuthSession(
        user_id=user_id,
        token_hash=hash_token(raw),
        expires_at=expires_at or NOW + timedelta(hours=12),
        revoked_at=revoked_at,
    )
    db.add(session)
    db.flush()
    client.cookies.set(get_settings().session_cookie_name, raw)
    return raw, session


def login(client, outbox, email):
    assert client.post("/api/auth/magic-link", json={"email": email}).status_code == 202
    url = outbox.outbox[-1][2].split("Sign in to Forte: ")[1].split()[0]
    token = parse_qs(urlparse(url).query)["token"][0]
    response = client.post("/api/auth/verify", json={"token": token})
    assert response.status_code == 200, response.text
    return response


def test_cookie_from_magic_link_works_on_next_request(client, db, outbox):
    company = f.make_company(db)
    employee = f.make_employee(db, company)
    member = f.make_member(db, company, Role.ADMIN, employee=employee)
    signed_in = login(client, outbox, employee.email)
    response = client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json() == signed_in.json()
    assert response.json()["membership"]["id"] == str(member.id)
    assert response.json()["onboarding"]["complete"] is True
    assert client.get("/api/runs").status_code == 200


def test_new_user_can_read_me_but_cannot_access_company_routes(client, outbox):
    signed_in = login(client, outbox, "new-admin@larkspur.example")
    response = client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json() == signed_in.json()
    assert response.json()["membership"] is None
    response = client.get("/api/runs")
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "no_company"


@pytest.mark.parametrize("endpoint", ["/api/auth/me", "/api/runs"])
@pytest.mark.parametrize(
    "condition",
    ["missing", "empty", "unknown", "tampered", "expired", "boundary", "revoked", "hash"],
)
def test_invalid_sessions_return_401(client, db, endpoint, condition):
    company = f.make_company(db)
    member = f.make_member(db, company)
    raw, session = session_cookie(db, client, member.user_id)
    if condition == "missing":
        client.cookies.clear()
    elif condition == "empty":
        client.cookies.set(get_settings().session_cookie_name, "")
    elif condition == "unknown":
        client.cookies.set(get_settings().session_cookie_name, "unknown")
    elif condition == "tampered":
        client.cookies.set(get_settings().session_cookie_name, raw + "x")
    elif condition == "hash":
        client.cookies.set(get_settings().session_cookie_name, session.token_hash)
    elif condition == "expired":
        session.expires_at = NOW - timedelta(seconds=1)
    elif condition == "boundary":
        session.expires_at = NOW
    elif condition == "revoked":
        session.revoked_at = NOW
    db.flush()
    response = client.get(endpoint)
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "unauthorized"


def test_logout_invalidates_copied_cookie(client, db, outbox):
    response = login(client, outbox, "logout-review@larkspur.example")
    cookie = response.cookies[get_settings().session_cookie_name]
    assert client.get("/api/auth/me").status_code == 200
    assert client.post("/api/auth/logout").status_code == 204
    # A stolen/copied cookie must fail even if the browser sends it again.
    client.cookies.set(get_settings().session_cookie_name, cookie)
    assert client.get("/api/auth/me").status_code == 401


@pytest.mark.parametrize("status", [MembershipStatus.REMOVED, MembershipStatus.INVITED])
def test_disallowed_membership_is_403(client, db, status):
    company = f.make_company(db)
    member = f.make_member(db, company, status=status)
    session_cookie(db, client, member.user_id)
    response = client.get("/api/runs")
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "forbidden"


def test_former_employee_can_read_paystubs_but_cannot_change_withholding(client, db):
    company = f.make_company(db)
    employee = f.make_employee(db, company)
    member = f.make_member(
        db, company, Role.EMPLOYEE, employee=employee, status=MembershipStatus.FORMER
    )
    session_cookie(db, client, member.user_id)
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["membership"]["status"] == "former"
    response = client.get("/api/me/paystubs")
    # A-06 has not landed on this branch; 501 proves the auth guard let us reach it.
    if response.status_code == 501:
        assert response.json()["detail"]["task"] == "A-06"
    else:
        assert response.status_code == 200
    response = client.put(
        "/api/me/withholding", json={"fed_filing_status": "single", "ca_filing_status": "single"}
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "forbidden"
    assert client.get("/api/runs").status_code == 403


def test_existing_cookie_uses_current_membership(client, db):
    company = f.make_company(db)
    member = f.make_member(db, company, Role.ADMIN)
    session_cookie(db, client, member.user_id)
    assert client.get("/api/runs").status_code == 200
    # Emulate another request changing the role, without refreshing the ORM identity map.
    db.execute(
        update(Membership)
        .where(Membership.id == member.id)
        .values(role=Role.EMPLOYEE)
        .execution_options(synchronize_session=False)
    )
    assert client.get("/api/runs").status_code == 403
    db.execute(
        update(Membership)
        .where(Membership.id == member.id)
        .values(status=MembershipStatus.REMOVED)
        .execution_options(synchronize_session=False)
    )
    assert client.get("/api/runs").status_code == 403
    assert client.get("/api/auth/me").status_code == 403


def test_real_cookie_scopes_runs_to_own_company(client, db):
    company = f.make_company(db)
    member = f.make_member(db, company)
    own = f.make_run(db, company)
    other, other_member = f.other_company_setup(db)
    foreign = f.make_run(db, other)
    session_cookie(db, client, member.user_id)
    response = client.get(
        f"/api/runs?company_id={other.id}",
        headers={"X-Company-Id": str(other.id), "X-User-Id": str(other_member.user_id)},
    )
    assert response.status_code == 200
    assert [run["id"] for run in response.json()] == [str(own.id)]
    response = client.get(f"/api/runs/{foreign.id}")
    assert response.status_code == 404


@pytest.mark.parametrize("resolver", [get_session_user, get_actor])
def test_identity_resolution_uses_one_joined_query(client, db, resolver):
    company = f.make_company(db)
    employee = f.make_employee(db, company)
    member = f.make_member(db, company, Role.PAYROLL_MANAGER, employee=employee)
    user = db.get(User, member.user_id)
    raw, _ = session_cookie(db, client, member.user_id)
    request = Request(
        {
            "type": "http",
            "client": ("127.0.0.7", 12345),
            "headers": [
                (b"cookie", f"{get_settings().session_cookie_name}={raw}".encode()),
                (b"x-forwarded-for", b"192.0.2.99"),
            ],
        }
    )
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    connection = db.connection()
    event.listen(connection, "before_cursor_execute", capture)
    try:
        identity = resolver(request, db)
        assert identity.user_id == user.id
        assert identity.email == user.email
        if resolver == get_actor:
            assert identity.membership_id == member.id
            assert identity.company_id == company.id
            assert identity.employee_id == employee.id
            assert identity.role == Role.PAYROLL_MANAGER
            assert identity.status == MembershipStatus.ACTIVE
            assert identity.ip == "127.0.0.7"
    finally:
        event.remove(connection, "before_cursor_execute", capture)
    assert len(statements) == 1
    assert "JOIN users" in statements[0]
    assert "LEFT OUTER JOIN memberships" in statements[0]


def test_custom_cookie_name(client, db, monkeypatch):
    company = f.make_company(db)
    member = f.make_member(db, company)
    raw, _ = session_cookie(db, client, member.user_id)
    settings = get_settings().model_copy(update={"session_cookie_name": "custom_session"})
    monkeypatch.setattr("app.auth.resolution.get_settings", lambda: settings)
    assert client.get("/api/runs").status_code == 401
    client.cookies.set("custom_session", raw)
    assert client.get("/api/runs").status_code == 200
