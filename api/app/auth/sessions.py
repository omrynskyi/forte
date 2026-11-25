"""B-01: server-side sessions, cookie lifecycle and signed-in-user responses.

Session cookies contain a fresh random secret; the DB stores only its SHA-256 hash.
All writes share the caller's transaction. B-02 owns cookie resolution in auth/deps.py.
Authentication bootstrap looks up membership by the verified user, not request company ids.
"""

import secrets
from datetime import timedelta

from fastapi import Request, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import audit, clock
from app.auth.deps import Actor
from app.auth.scoping import get_scoped
from app.auth.tokens import hash_token
from app.config import get_settings
from app.errors import Forbidden
from app.models import AuthSession, Company, Employee, Membership, User
from app.models.enums import MembershipStatus
from app.schemas.auth import CompanyBrief, MembershipBrief, MeOut, OnboardingStatus
from app.services.readiness import readiness


def user_membership(db: Session, user: User, *, lock: bool = False) -> Membership | None:
    stmt = select(Membership).where(Membership.user_id == user.id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return db.scalar(stmt)


def create_session(db: Session, user: User, request: Request) -> str:
    """Activate invited members, audit sign-in and issue a session; removed members stay blocked."""
    member = user_membership(db, user, lock=True)
    if member and member.status == MembershipStatus.REMOVED:
        raise Forbidden("Your access to this company has been removed.")
    previous_status = member.status if member else None
    if member and member.status == MembershipStatus.INVITED:
        member.status = MembershipStatus.ACTIVE
    now = clock.now()
    raw = secrets.token_urlsafe(32)
    ip = request.client.host[:64] if request.client else None
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=hash_token(raw),
            expires_at=now + timedelta(hours=get_settings().session_ttl_hours),
            ip=ip,
            user_agent=request.headers.get("user-agent", "")[:400],
        )
    )
    user.last_login_at = now
    actor = (
        Actor(
            user_id=user.id,
            email=user.email,
            membership_id=member.id,
            company_id=member.company_id,
            role=member.role,
            status=member.status,
            employee_id=member.employee_id,
            ip=ip,
        )
        if member
        else None
    )
    entry = audit.record(
        db,
        actor=actor,
        action=audit.USER_SIGNED_IN,
        entity_type="user",
        entity_id=user.id,
        before={"membership_status": previous_status},
        after={"membership_status": member.status if member else None},
    )
    # New signups have no Actor yet; still attribute their sign-in to the verified user.
    entry.actor_user_id = user.id
    entry.ip = ip
    db.flush()
    return raw


def revoke_session(db: Session, token: str | None) -> None:
    """Idempotent logout; missing or unknown cookies are already signed out."""
    if token:
        db.execute(
            update(AuthSession)
            .where(AuthSession.token_hash == hash_token(token), AuthSession.revoked_at.is_(None))
            .values(revoked_at=clock.now())
        )


def set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_ttl_hours * 3600,
        path="/",
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"


def clear_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"


def build_me(db: Session, user: User) -> MeOut:
    member = user_membership(db, user)
    if member and member.status == MembershipStatus.REMOVED:
        raise Forbidden("Your access to this company has been removed.")
    company = None
    employee = None
    onboarding = None
    if member:
        # The verified membership is the trusted tenant boundary during login bootstrap.
        actor = Actor(
            user_id=user.id,
            email=user.email,
            membership_id=member.id,
            company_id=member.company_id,
            role=member.role,
            status=member.status,
            employee_id=member.employee_id,
        )
        company = db.get(Company, member.company_id)
        if member.employee_id:
            employee = get_scoped(db, Employee, member.employee_id, actor)
            ready = readiness(db, employee, clock.today_pacific())
            onboarding = OnboardingStatus(
                personal_info=ready.personal_info,
                withholding=ready.withholding,
                bank_account=ready.bank_account,
                complete=ready.onboarding_complete,
            )
    return MeOut(
        user_id=user.id,
        email=user.email,
        display_name=f"{employee.first_name} {employee.last_name}" if employee else None,
        membership=MembershipBrief.model_validate(member) if member else None,
        company=CompanyBrief(
            id=company.id,
            legal_name=company.legal_name,
            setup_complete=company.setup_completed_at is not None,
        )
        if company
        else None,
        employee_id=employee.id if employee else None,
        onboarding=onboarding,
    )
