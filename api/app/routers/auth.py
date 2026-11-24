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

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.adapters import get_email_sender
from app.adapters.email import EmailSender
from app.auth.deps import SessionUser, get_session_user
from app.db import get_db
from app.errors import todo
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
    todo("B-01")


@router.post("/verify", response_model=MeOut)
def verify_magic_link(body: VerifyRequest, response: Response, db: Session = Depends(get_db)):
    todo("B-01")


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, db: Session = Depends(get_db)):
    todo("B-01")


@router.get("/me", response_model=MeOut)
def me(user: SessionUser = Depends(get_session_user), db: Session = Depends(get_db)):
    """Works with or without a membership (a brand-new Admin has none until POST /api/companies)."""
    todo("B-01")


@router.get("/dev/users", response_model=list[DevUserOut])
def dev_users(db: Session = Depends(get_db)):
    """Dev switcher: every user with their role, for one-click sign-in during rehearsals."""
    todo("B-01")


@router.post("/dev/login", response_model=MeOut)
def dev_login(body: DevLoginRequest, response: Response, db: Session = Depends(get_db)):
    todo("B-01")
