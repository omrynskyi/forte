import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Identity, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AuditLog(Base):
    """AUD-1/AUD-2. Insert-only: a DB trigger (migration 0001) raises on UPDATE or DELETE.
    Write entries ONLY through app.audit.record(), inside the same transaction as the change."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id"), index=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    actor_membership_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("memberships.id"))
    action: Mapped[str] = mapped_column(String(64))  # e.g. "run.approved"; see app/audit.py
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(64))
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    ip: Mapped[str | None] = mapped_column(String(64))


class Notification(Base):
    """Every email we send (magic links, invites). Email only in the MVP."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))  # "magic_link" | "invite"
    subject: Mapped[str] = mapped_column(String(200))
    sent_at: Mapped[datetime | None]
