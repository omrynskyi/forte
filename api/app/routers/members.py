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
from sqlalchemy.orm import Session

from app.adapters import get_email_sender
from app.adapters.email import EmailSender
from app.auth.deps import Actor, require_admin, require_staff
from app.db import get_db
from app.errors import todo
from app.schemas.members import InviteIn, MemberOut, RoleChangeIn

router = APIRouter(prefix="/api/members", tags=["members"])


@router.get("", response_model=list[MemberOut])
def list_members(actor: Actor = Depends(require_staff), db: Session = Depends(get_db)):
    todo("B-04")


@router.post("/invite", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
def invite_member(
    body: InviteIn,
    actor: Actor = Depends(require_admin),
    db: Session = Depends(get_db),
    email: EmailSender = Depends(get_email_sender),
):
    todo("B-04")


@router.patch("/{membership_id}", response_model=MemberOut)
def change_role(
    membership_id: uuid.UUID,
    body: RoleChangeIn,
    actor: Actor = Depends(require_admin),
    db: Session = Depends(get_db),
):
    todo("B-04")


@router.delete("/{membership_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    membership_id: uuid.UUID, actor: Actor = Depends(require_admin), db: Session = Depends(get_db)
):
    todo("B-04")
