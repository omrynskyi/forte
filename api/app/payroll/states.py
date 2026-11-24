"""The payroll run state machine, as data (D7). This table is the single source of truth: the
service (state_machine.py), the API's `allowed_actions`, the UI buttons, and the tests all read it.

    draft ──submit──▶ submitted ──approve──▶ approved ──start_processing──▶ processing ──mark_paid──▶ paid
      ▲                  │                                                     │
      └─return_to_draft──┘                                                     └─mark_failed─▶ failed
    draft/submitted ──cancel──▶ cancelled                                       failed ──retry──▶ processing

Who may fire each action:
- "staff"  = Admin or Payroll Manager
- "admin"  = Admin only (RUN-3: only an Admin can approve or cancel)
- "system" = the app itself (after approval, or the payments webhook). Never exposed as an endpoint.
"""

from enum import StrEnum
from typing import Literal

from app.models.enums import RunState

ActorKind = Literal["staff", "admin", "system"]


class RunAction(StrEnum):
    SUBMIT = "submit"
    RETURN_TO_DRAFT = "return_to_draft"
    CANCEL = "cancel"
    APPROVE = "approve"
    START_PROCESSING = "start_processing"
    MARK_PAID = "mark_paid"
    MARK_FAILED = "mark_failed"
    RETRY = "retry"


S = RunState
A = RunAction

TRANSITIONS: dict[tuple[RunState, RunAction], tuple[RunState, ActorKind]] = {
    (S.DRAFT, A.SUBMIT): (S.SUBMITTED, "staff"),
    (S.SUBMITTED, A.RETURN_TO_DRAFT): (S.DRAFT, "staff"),
    (S.DRAFT, A.CANCEL): (S.CANCELLED, "admin"),
    (S.SUBMITTED, A.CANCEL): (S.CANCELLED, "admin"),
    (S.SUBMITTED, A.APPROVE): (S.APPROVED, "admin"),
    (S.APPROVED, A.START_PROCESSING): (S.PROCESSING, "system"),
    (S.PROCESSING, A.MARK_PAID): (S.PAID, "system"),
    (S.PROCESSING, A.MARK_FAILED): (S.FAILED, "system"),
    (S.FAILED, A.RETRY): (S.PROCESSING, "admin"),
}

TERMINAL_STATES = frozenset({S.PAID, S.CANCELLED})
# Items and totals may change only in DRAFT (enforced by a DB trigger too).
EDITABLE_STATES = frozenset({S.DRAFT})
# Employees see a "preview, not final" paystub in these states (PAY-2).
PREVIEW_STATES = frozenset({S.SUBMITTED, S.APPROVED, S.PROCESSING, S.FAILED})


def next_state(state: RunState, action: RunAction) -> RunState | None:
    hit = TRANSITIONS.get((state, action))
    return hit[0] if hit else None


def actions_from(state: RunState) -> list[RunAction]:
    return [action for (s, action) in TRANSITIONS if s == state]


CorrectionStatus = Literal["opened", "in_review", "approved", "paid", "cancelled"]


def correction_status(run_state: RunState) -> CorrectionStatus:
    """COR-2: what the employee sees, derived from the correction run's state."""
    return {
        S.DRAFT: "opened",
        S.SUBMITTED: "in_review",
        S.APPROVED: "approved",
        S.PROCESSING: "approved",
        S.FAILED: "approved",
        S.PAID: "paid",
        S.CANCELLED: "cancelled",
    }[run_state]
