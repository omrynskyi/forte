"""Who is calling, and are they allowed? (AUTH-3)

Every protected endpoint takes `actor: Actor = Depends(get_actor)` (or one of the role helpers).
`Actor.company_id` is the ONLY source of the tenant for a request. Never trust a company_id that
arrives in a path, query or body.

Tests don't need real sessions: use the `as_role` fixture in tests/conftest.py, which overrides
`get_actor` for the duration of a test.
"""

import uuid
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import Forbidden
from app.models.enums import MembershipStatus, Role


@dataclass(frozen=True)
class Actor:
    user_id: uuid.UUID
    email: str
    membership_id: uuid.UUID
    company_id: uuid.UUID
    role: Role
    status: MembershipStatus
    employee_id: uuid.UUID | None  # set when this member is on payroll
    ip: str | None = None

    @property
    def is_former(self) -> bool:
        return self.status == MembershipStatus.FORMER


@dataclass(frozen=True)
class SessionUser:
    """A signed-in user who may not belong to a company yet (between magic link and company setup)."""

    user_id: uuid.UUID
    email: str


def get_session_user(request: Request, db: Session = Depends(get_db)) -> SessionUser:
    """Resolve the session cookie to a user. Raises 401 if missing/expired/revoked. Task B-02."""
    from app.auth.resolution import resolve_identity

    user, _ = resolve_identity(request, db)
    return SessionUser(user_id=user.id, email=user.email)


def get_actor(request: Request, db: Session = Depends(get_db)) -> Actor:
    """Resolve the session cookie to an Actor with an active (or former) membership.
    401 if not signed in, 403 if the user has no membership or it was REMOVED. Task B-02."""
    from app.auth.resolution import resolve_identity

    user, member = resolve_identity(request, db)
    if member is None:
        raise Forbidden("Create or join a company to continue.", code="no_company")
    if member.status not in (MembershipStatus.ACTIVE, MembershipStatus.FORMER):
        raise Forbidden("Your membership does not allow access to this company.")
    return Actor(
        user_id=user.id,
        email=user.email,
        membership_id=member.id,
        company_id=member.company_id,
        role=member.role,
        status=member.status,
        employee_id=member.employee_id,
        ip=request.client.host if request.client else None,
    )


def require_roles(*roles: Role, allow_former: bool = False):  # noqa: ANN201
    """Dependency factory: `actor: Actor = Depends(require_roles(Role.ADMIN))`.
    Former employees are rejected unless allow_former=True (only for their own paystubs)."""

    def dep(actor: Actor = Depends(get_actor)) -> Actor:
        if actor.is_former and not allow_former:
            raise Forbidden("Former employees have read-only access to their own documents.")
        if actor.role not in roles:
            raise Forbidden("You don't have permission to do that.")
        return actor

    return dep


STAFF = (Role.ADMIN, Role.PAYROLL_MANAGER)
require_admin = require_roles(Role.ADMIN)
require_staff = require_roles(*STAFF)


def require_employee_self(allow_former: bool = False):  # noqa: ANN201
    """Any member who is on payroll (has employee_id), acting on their own record."""

    def dep(actor: Actor = Depends(get_actor)) -> Actor:
        if actor.is_former and not allow_former:
            raise Forbidden("Former employees have read-only access to their own documents.")
        if actor.employee_id is None:
            raise Forbidden("You're not on payroll at this company.")
        return actor

    return dep
