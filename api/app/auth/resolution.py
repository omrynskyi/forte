"""B-02: resolve a session cookie and its current membership in one database query.

Authentication bootstrap uses the session's user id to discover the trusted company;
company ids and forwarding headers supplied by the client never determine identity.
"""

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.auth.tokens import hash_token
from app.config import get_settings
from app.errors import Unauthorized
from app.models import AuthSession, Membership, User


def resolve_identity(request: Request, db: Session) -> tuple[User, Membership | None]:
    token = request.cookies.get(get_settings().session_cookie_name)
    if not token:
        raise Unauthorized("Sign in to continue.")
    identity = db.execute(
        select(User, Membership)
        .select_from(AuthSession)
        .join(User, User.id == AuthSession.user_id)
        .outerjoin(Membership, Membership.user_id == User.id)
        .where(
            AuthSession.token_hash == hash_token(token),
            AuthSession.expires_at > clock.now(),
            AuthSession.revoked_at.is_(None),
        )
        .execution_options(populate_existing=True)
    ).one_or_none()
    if identity is None:
        raise Unauthorized("Your session is invalid or has expired. Sign in again.")
    return identity[0], identity[1]
