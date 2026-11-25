"""B-01: issue emailed login/invite tokens and consume them exactly once.

Only SHA-256 hashes are persisted. The raw token exists only in the outgoing email.
Consumption locks the token until the caller's transaction ends; callers must create the
session in that same transaction. These helpers flush but never commit.
"""

import hashlib
import secrets
from datetime import timedelta
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.adapters.email import EmailSender
from app.config import get_settings
from app.errors import Unauthorized
from app.models import MagicLinkToken, Membership, Notification, User
from app.models.enums import MagicLinkPurpose


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_magic_link(
    db: Session, user: User, purpose: MagicLinkPurpose, email: EmailSender
) -> None:
    """Reusable by B-04/B-05 for invitations; never return or persist the raw link."""
    settings = get_settings()
    purpose = MagicLinkPurpose(purpose)
    raw = secrets.token_urlsafe(32)
    db.add(
        MagicLinkToken(
            user_id=user.id,
            token_hash=hash_token(raw),
            purpose=purpose,
            expires_at=clock.now() + timedelta(minutes=settings.magic_link_ttl_minutes),
        )
    )
    # Authentication bootstrap: the recipient's DB membership determines the tenant,
    # never a company id supplied by the request.
    member = db.scalar(select(Membership).where(Membership.user_id == user.id))
    subject = "Your Forte invitation" if purpose == MagicLinkPurpose.INVITE else "Sign in to Forte"
    notification = Notification(
        company_id=member.company_id if member else None,
        user_id=user.id,
        kind="invite" if purpose == MagicLinkPurpose.INVITE else "magic_link",
        subject=subject,
    )
    db.add(notification)
    db.flush()
    link = f"{settings.web_base_url.rstrip('/')}/auth/verify?{urlencode({'token': raw})}"
    email.send(
        user.email,
        subject,
        f"Sign in to Forte: {link}\n\nThis link works once, for {settings.magic_link_ttl_minutes} minutes.",
    )
    notification.sent_at = clock.now()
    db.flush()


def consume_magic_link(db: Session, token: str) -> User:
    db.flush()
    link = db.scalar(
        select(MagicLinkToken)
        .where(MagicLinkToken.token_hash == hash_token(token))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if link is None:
        raise Unauthorized("This sign-in link is invalid.", code="link_invalid")
    if link.used_at is not None:
        raise Unauthorized("This sign-in link has already been used.", code="link_used")
    if clock.now() >= link.expires_at:
        raise Unauthorized("This sign-in link has expired. Request a new one.", code="link_expired")
    link.used_at = clock.now()
    db.flush()
    return db.get(User, link.user_id)
