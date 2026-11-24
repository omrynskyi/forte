"""AUD-1 / NFR-10: every change to pay, bank details, roles or run state writes an audit entry in
the SAME transaction as the change. Call `record()` right after you mutate, before the request ends.

Never log secrets: pass masked values (last 4) for SSN / account numbers, never the full value.

Action names are "<entity>.<verb>" in past tense. Use the constants below so the audit page (B-08)
can render a sentence for each one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.models import AuditLog

if TYPE_CHECKING:
    from app.auth.deps import Actor

# --- action names (add new ones here, and a sentence for it in B-08's renderer) ---
COMPANY_CREATED = "company.created"
COMPANY_UPDATED = "company.updated"
FUNDING_ACCOUNT_CONNECTED = "funding_account.connected"
PAY_SCHEDULE_SET = "pay_schedule.set"
MEMBER_INVITED = "member.invited"
MEMBER_ROLE_CHANGED = "member.role_changed"
MEMBER_REMOVED = "member.removed"
USER_SIGNED_IN = "user.signed_in"
EMPLOYEE_CREATED = "employee.created"
EMPLOYEE_UPDATED = "employee.updated"
EMPLOYEE_PERSONAL_INFO_SET = "employee.personal_info_set"
EMPLOYEE_TERMINATED = "employee.terminated"
COMPENSATION_SET = "compensation.set"
WITHHOLDING_SET = "withholding.set"
BANK_ACCOUNT_SET = "bank_account.set"
SENSITIVE_FIELD_REVEALED = "sensitive_field.revealed"
TIMESHEET_APPROVED = "timesheet.approved"
TIMESHEET_REJECTED = "timesheet.rejected"
TIMESHEETS_LOCKED = "timesheets.locked"
RUN_CREATED = "run.created"
RUN_RECALCULATED = "run.recalculated"
RUN_TRANSITIONED = "run.transitioned"  # before/after carry {"state": ...}
CORRECTION_OPENED = "correction.opened"


def record(
    session: Session,
    *,
    actor: Actor | None,
    action: str,
    entity_type: str,
    entity_id: object,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    company_id: object | None = None,
) -> AuditLog:
    """Add an audit row to the current transaction. `actor=None` means the system (e.g. webhook)."""
    entry = AuditLog(
        company_id=company_id if company_id is not None else (actor.company_id if actor else None),
        actor_user_id=actor.user_id if actor else None,
        actor_membership_id=actor.membership_id if actor else None,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        before=_jsonable(before),
        after=_jsonable(after),
        ip=actor.ip if actor else None,
    )
    session.add(entry)
    return entry


def _jsonable(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if data is None:
        return None
    return {
        k: (v if isinstance(v, (str, int, bool, type(None), list, dict)) else str(v))
        for k, v in data.items()
    }
