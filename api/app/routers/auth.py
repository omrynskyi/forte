"""Auth (AUTH-1, AUTH-2). Task B-01. Magic links only; passkeys are cut (D3).

Rules:
- POST /magic-link always returns 202 with the same message (no account enumeration). If the
  email is unknown, create the User anyway (that's how a new Admin signs up, Journey 1).
- Token: secrets.token_urlsafe(32); store sha256 hex only; expires in settings.magic_link_ttl_minutes;
  single use (set used_at; a second verify -> 401 code "link_used"; expired -> 401 "link_expired").
- Link: f"{settings.web_base_url}/auth/verify?token=<token>". Send via get_email_sender().
- On verify: create AuthSession, set cookie settings.session_cookie_name (HttpOnly, SameSite=Lax,
  Secure=settings.session_cookie_secure, Path=/, Max-Age=session_ttl_hours). INVITED membership
  becomes ACTIVE. Audit USER_SIGNED_IN.
- Dev login (D10): only when settings.dev_login_enabled and env != "prod", else 404.
"""

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.adapters import get_email_sender
from app.adapters.email import EmailSender
from app.auth.deps import SessionUser, get_session_user
from app.auth.sessions import (
    build_me,
    clear_session_cookie,
    create_session,
    revoke_session,
    set_session_cookie,
)
from app.auth.tokens import consume_magic_link, issue_magic_link
from app.config import get_settings
from app.db import get_db
from app.errors import NotFound, Unauthorized
from app.models import Membership, User
from app.models.enums import MagicLinkPurpose, MembershipStatus
from app.schemas.auth import (
    DevLoginRequest,
    DevUserOut,
    MagicLinkAccepted,
    MagicLinkRequest,
    MeOut,
    VerifyRequest,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/magic-link", response_model=MagicLinkAccepted, status_code=status.HTTP_202_ACCEPTED)
def request_magic_link(
    body: MagicLinkRequest,
    db: Session = Depends(get_db),
    email: EmailSender = Depends(get_email_sender),
):
    normalized = str(body.email).lower()
    # ON CONFLICT also handles simultaneous first-time requests for the same email.
    db.execute(
        insert(User).values(email=normalized).on_conflict_do_nothing(index_elements=[User.email])
    )
    user = db.scalar(select(User).where(User.email == normalized))
    issue_magic_link(db, user, MagicLinkPurpose.LOGIN, email)
    return MagicLinkAccepted()


@router.post("/verify", response_model=MeOut)
def verify_magic_link(
    body: VerifyRequest, response: Response, request: Request, db: Session = Depends(get_db)
):
    user = consume_magic_link(db, body.token)
    token = create_session(db, user, request)
    result = build_me(db, user)
    set_session_cookie(response, token)
    return result


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, request: Request, db: Session = Depends(get_db)):
    revoke_session(db, request.cookies.get(get_settings().session_cookie_name))
    clear_session_cookie(response)


@router.get("/me", response_model=MeOut)
def me(
    response: Response, user: SessionUser = Depends(get_session_user), db: Session = Depends(get_db)
):
    """Works with or without a membership (a brand-new Admin has none until POST /api/companies)."""
    stored = db.get(User, user.user_id)
    if stored is None:
        raise Unauthorized("Your session is no longer valid.")
    response.headers["Cache-Control"] = "no-store"
    return build_me(db, stored)


@router.get("/dev/users", response_model=list[DevUserOut])
def dev_users(db: Session = Depends(get_db)):
    """Dev switcher: every user with their role, for one-click sign-in during rehearsals."""
    _require_dev_login()
    # Intentionally cross-company only in the gated development switcher.
    users = db.scalars(
        select(User)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.status != MembershipStatus.REMOVED)
        .order_by(User.email)
    ).all()
    result = []
    for user in users:
        info = build_me(db, user)
        result.append(
            DevUserOut(
                email=user.email,
                display_name=info.display_name or user.email,
                role=info.membership.role,
                status=info.membership.status,
            )
        )
    return result


@router.post("/dev/login", response_model=MeOut)
def dev_login(
    body: DevLoginRequest, response: Response, request: Request, db: Session = Depends(get_db)
):
    _require_dev_login()
    user = db.scalar(select(User).where(User.email == str(body.email).lower()))
    if user is None:
        raise NotFound("User not found.")
    token = create_session(db, user, request)
    result = build_me(db, user)
    set_session_cookie(response, token)
    return result


def _require_dev_login() -> None:
    settings = get_settings()
    if not settings.dev_login_enabled or settings.is_prod:
        raise NotFound("Not found.")
