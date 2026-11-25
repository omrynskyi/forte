"""Audit log (AUD-1, AUD-2). Task B-08.

- Admin: everything in the company. Payroll Manager: only entries where they are the actor.
- Filters: entity_type, entity_id, action, limit (default 100, max 500). Newest first.
- `summary` comes from app/services/audit_text.py::summarize(entry, names) which this task creates:
  one plain sentence per action constant in app/audit.py.
- There is no update or delete endpoint, and the DB trigger rejects both anyway (AUD-2).
"""

import uuid
from collections import defaultdict

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import Actor, require_staff
from app.auth.scoping import scoped
from app.db import get_db
from app.models import AuditLog, Employee, Membership, PayrollRun, User
from app.models.enums import Role
from app.schemas.audit import AuditEntryOut
from app.services.audit_text import format_date, summarize

router = APIRouter(prefix="/api/audit", tags=["audit"])


def _uuid(value: str | None) -> uuid.UUID | None:
    try:
        return uuid.UUID(value) if value else None
    except ValueError:
        return None


@router.get("", response_model=list[AuditEntryOut])
def list_audit(
    entity_type: str | None = None,
    entity_id: str | None = None,
    action: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    actor: Actor = Depends(require_staff),
    db: Session = Depends(get_db),
):
    stmt = scoped(select(AuditLog), AuditLog, actor)
    if actor.role != Role.ADMIN:
        stmt = stmt.where(AuditLog.actor_membership_id == actor.membership_id)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    entries = list(
        db.scalars(stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit))
    )

    # Resolve names with a few company-scoped batch queries.
    by_type: dict[str, set[uuid.UUID]] = defaultdict(set)
    for e in entries:
        if (u := _uuid(e.entity_id)) is not None:
            by_type[e.entity_type].add(u)

    member_ids = {e.actor_membership_id for e in entries if e.actor_membership_id}
    member_ids |= by_type["membership"] | by_type["member"]
    members: dict[uuid.UUID, Membership] = {}
    if member_ids:
        members = {
            m.id: m
            for m in db.scalars(
                scoped(select(Membership), Membership, actor).where(Membership.id.in_(member_ids))
            )
        }
    employee_ids = set(by_type["employee"]) | {
        m.employee_id for m in members.values() if m.employee_id
    }
    employees: dict[uuid.UUID, Employee] = {}
    if employee_ids:
        employees = {
            emp.id: emp
            for emp in db.scalars(
                scoped(select(Employee), Employee, actor).where(Employee.id.in_(employee_ids))
            )
        }
    users: dict[uuid.UUID, User] = {}
    if members:
        users = {
            u.id: u
            for u in db.scalars(
                select(User).where(User.id.in_({m.user_id for m in members.values()}))
            )
        }
    runs: dict[uuid.UUID, PayrollRun] = {}
    if by_type["payroll_run"]:
        runs = {
            r.id: r
            for r in db.scalars(
                scoped(select(PayrollRun), PayrollRun, actor).where(
                    PayrollRun.id.in_(by_type["payroll_run"])
                )
            )
        }

    def member_name(m: Membership) -> str:
        emp = employees.get(m.employee_id) if m.employee_id else None
        if emp:
            return f"{emp.first_name} {emp.last_name}"
        user = users.get(m.user_id)
        return user.email if user else "A team member"

    out: list[AuditEntryOut] = []
    for e in entries:
        names: dict[str, str] = {}
        member = members.get(e.actor_membership_id) if e.actor_membership_id else None
        if member:
            names["actor"] = member_name(member)
        eid = _uuid(e.entity_id)
        if e.entity_type == "employee" and eid in employees:
            emp = employees[eid]
            names["entity"] = f"{emp.first_name} {emp.last_name}"
        elif e.entity_type in ("membership", "member") and eid in members:
            names["entity"] = member_name(members[eid])
        elif e.entity_type == "payroll_run" and eid in runs:
            names["pay_date"] = format_date(runs[eid].pay_date)
        out.append(
            AuditEntryOut(
                id=e.id,
                created_at=e.created_at,
                actor_name=names.get("actor"),
                actor_role=member.role.value if member else None,
                action=e.action,
                entity_type=e.entity_type,
                entity_id=e.entity_id,
                summary=summarize(e, names),
                before=e.before,
                after=e.after,
            )
        )
    return out
