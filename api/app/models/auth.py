import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, enum_col
from app.models.enums import MagicLinkPurpose


class User(IdMixin, Base):
    """A person who can sign in. Not company-scoped: a user exists before their company does."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True)  # always stored lowercase
    last_login_at: Mapped[datetime | None]


class MagicLinkToken(IdMixin, Base):
    """AUTH-2: expires after 15 minutes and works once. Only the SHA-256 hash is stored."""

    __tablename__ = "magic_link_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    purpose: Mapped[MagicLinkPurpose] = mapped_column(enum_col(MagicLinkPurpose))
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]


class AuthSession(IdMixin, Base):
    """Server-side session. The cookie holds a random token; only its SHA-256 hash is stored."""

    __tablename__ = "auth_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(400))
