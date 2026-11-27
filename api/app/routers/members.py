"""Team and roles (CO-4, CO-5). Task B-04.

- Only Admins invite Admins/Payroll Managers. Payroll Managers invite Employees only, and that
  happens through POST /api/employees (decision D17).
- CO-5: never leave a company with zero ACTIVE Admins (role change or removal) -> 409 "last_admin".
- Nobody changes their own role.
- Invite = create User if needed + INVITED membership + magic link with purpose INVITE (reuse B-01's
  issue_magic_link helper). Audit MEMBER_INVITED / MEMBER_ROLE_CHANGED / MEMBER_REMOVED.
"""

import uuid

from fastapi import APIRouter, Depends, status
from fastapi.routing import APIRoute
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app import audit
from app.adapters import get_email_sender
from app.adapters.email import EmailSender
from app.auth.deps import Actor, require_admin, require_staff
from app.auth.scoping import get_scoped, scoped
from app.auth.tokens import issue_magic_link
from app.db import get_db
from app.errors import Conflict, Forbidden, NotFound
from app.models import Company, Employee, Membership, User
from app.models.enums import MagicLinkPurpose, MembershipStatus, Role
from app.schemas.members import InviteIn, MemberOut, RoleChangeIn


class MemberRoute(APIRoute):
    """Team access information must not be cached by browsers or proxies."""

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def no_store(request):
            response = await handler(request)
            response.headers["Cache-Control"] = "no-store"
            return response

        return no_store


router = APIRouter(prefix="/api/members", tags=["members"], route_class=MemberRoute)


@router.get("", response_model=list[MemberOut])
def list_members(actor: Actor = Depends(require_staff), db: Session = Depends(get_db)):
    rows = db.execute(
        scoped(
            select(Membership, User).join(User, User.id == Membership.user_id), Membership, actor
        ).order_by(User.email)
    ).all()
    return [_member_out(db, member, user, actor) for member, user in rows]


@router.post("/invite", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
def invite_member(
    body: InviteIn,
    actor: Actor = Depends(require_admin),
    db: Session = Depends(get_db),
    email: EmailSender = Depends(get_email_sender),
):
    _lock_admin_company(db, actor)
    normalized = str(body.email).lower()
    db.execute(
        insert(User).values(email=normalized).on_conflict_do_nothing(index_elements=[User.email])
    )
    user = db.scalar(select(User).where(User.email == normalized).with_for_update())
    # Bootstrap lookup: user membership is globally unique (D22). Do not disclose
    # whether a conflicting membership belongs to this company or another one.
    if db.scalar(select(Membership.id).where(Membership.user_id == user.id)) is not None:
        raise Conflict(
            "This email already has a membership and cannot be invited.", code="email_in_use"
        )
    member = Membership(
        company_id=actor.company_id,
        user_id=user.id,
        role=Role(body.role),
        status=MembershipStatus.INVITED,
        invited_by_membership_id=actor.membership_id,
    )
    db.add(member)
    db.flush()
    audit.record(
        db,
        actor=actor,
        action=audit.MEMBER_INVITED,
        entity_type="membership",
        entity_id=member.id,
        after={"email": user.email, "role": member.role, "status": member.status},
    )
    issue_magic_link(db, user, MagicLinkPurpose.INVITE, email)
    return _member_out(db, member, user, actor)


@router.patch("/{membership_id}", response_model=MemberOut)
def change_role(
    membership_id: uuid.UUID,
    body: RoleChangeIn,
    actor: Actor = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _lock_admin_company(db, actor)
    member = get_scoped(db, Membership, membership_id, actor)
    db.refresh(member, with_for_update=True)
    role = Role(body.role)
    if member.status == MembershipStatus.REMOVED:
        raise Conflict("This member's access has been removed.", code="member_removed")
    if role != member.role:
        _ensure_admin_remains(db, member, actor)
        if member.id == actor.membership_id:
            raise Conflict("Another Admin must change your role.", code="own_role")
        old_role = member.role
        member.role = role
        audit.record(
            db,
            actor=actor,
            action=audit.MEMBER_ROLE_CHANGED,
            entity_type="membership",
            entity_id=member.id,
            before={"role": old_role},
            after={"role": member.role},
        )
        db.flush()
    return _member_out(db, member, db.get(User, member.user_id), actor)


@router.delete("/{membership_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    membership_id: uuid.UUID, actor: Actor = Depends(require_admin), db: Session = Depends(get_db)
):
    _lock_admin_company(db, actor)
    member = get_scoped(db, Membership, membership_id, actor)
    db.refresh(member, with_for_update=True)
    if member.status == MembershipStatus.REMOVED:
        return
    # D21: former employees retain read-only document access indefinitely.
    if member.status == MembershipStatus.FORMER:
        raise Conflict(
            "Former employees retain read-only access to their documents.", code="former_member"
        )
    _ensure_admin_remains(db, member, actor)
    old_status = member.status
    member.status = MembershipStatus.REMOVED
    audit.record(
        db,
        actor=actor,
        action=audit.MEMBER_REMOVED,
        entity_type="membership",
        entity_id=member.id,
        before={"status": old_status, "role": member.role},
        after={"status": member.status, "role": member.role},
    )
    db.flush()


def _lock_admin_company(db: Session, actor: Actor) -> None:
    """Serialize access changes and recheck authorization after waiting for the lock.

    B-02 checked the caller when the request began; a concurrent Admin may have
    demoted/removed them while they waited. Do not proceed using that stale Actor.
    """
    company = db.scalar(select(Company).where(Company.id == actor.company_id).with_for_update())
    if company is None:
        raise NotFound("Company not found.")
    member = db.scalar(
        scoped(select(Membership), Membership, actor)
        .where(Membership.id == actor.membership_id, Membership.user_id == actor.user_id)
        .execution_options(populate_existing=True)
    )
    if member is None or member.role != Role.ADMIN or member.status != MembershipStatus.ACTIVE:
        raise Forbidden("Only an active Admin can change team access.")


def _ensure_admin_remains(db: Session, member: Membership, actor: Actor) -> None:
    """Caller holds the company lock. Invited/former/removed Admins don't count."""
    if member.role != Role.ADMIN or member.status != MembershipStatus.ACTIVE:
        return
    count = db.scalar(
        scoped(select(func.count()).select_from(Membership), Membership, actor).where(
            Membership.role == Role.ADMIN, Membership.status == MembershipStatus.ACTIVE
        )
    )
    if count <= 1:
        raise Conflict("Your company must keep at least one active Admin.", code="last_admin")


def _member_out(db: Session, member: Membership, user: User, actor: Actor) -> MemberOut:
    name = None
    if member.employee_id:
        employee = get_scoped(db, Employee, member.employee_id, actor)
        name = f"{employee.first_name} {employee.last_name}"
    return MemberOut(
        id=member.id,
        email=user.email,
        display_name=name,
        role=member.role,
        status=member.status,
        employee_id=member.employee_id,
        created_at=member.created_at,
    )
