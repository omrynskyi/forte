"""The ONLY code allowed to change PayrollRun.state (D7, NFR-4, NFR-10). Task A-02.

Contract:

    def transition(db, run_id, action, *, actor: Actor | None, note: str | None = None) -> PayrollRun

1. Lock the row: `db.execute(select(PayrollRun).where(PayrollRun.id == run_id).with_for_update())`.
   Also check tenant: if actor is given, run.company_id must equal actor.company_id (else NotFound).
2. Look up (run.state, action) in states.TRANSITIONS. Missing -> Conflict(code="illegal_transition").
3. Check who: "system" actions require actor=None; "admin" requires actor.role == ADMIN;
   "staff" requires ADMIN or PAYROLL_MANAGER. Wrong actor -> Forbidden.
4. Guards (raise Conflict with a specific code and a plain-language message):
   - SUBMIT: run has at least one item ("empty_run").
   - APPROVE: actor.membership_id != run.submitted_by_membership_id ("separation_of_duties").
   - APPROVE on a REGULAR run: clock.now() < pay_period.cutoff_at ("past_cutoff").
5. Set state + the matching *_by / *_at columns (submitted_at, approved_at, cancelled_at,
   processing_at, paid_at, failed_at, failure_reason from `note` on MARK_FAILED).
6. audit.record(action=audit.RUN_TRANSITIONED, entity_type="payroll_run", entity_id=run.id,
   before={"state": old}, after={"state": new, "action": action}, company_id=run.company_id).
7. Do NOT commit. The caller's transaction commits (get_db, or the webhook handler).

    def allowed_actions_for(db, run, actor) -> list[RunAction]

The actions THIS actor could fire on the run right now: the table's actions from run.state, kept
only if the actor's role fits and every guard above passes (so the list never offers a button that
would 409). Never returns system actions. The API puts it in RunDetail.allowed_actions (A-04).

Column details for step 5:
   - RETURN_TO_DRAFT clears submitted_at / submitted_by: the run is a draft again, and the next
     SUBMIT records whoever submits it then. The history stays in the audit log.
   - RETRY sets processing_at again and clears failure_reason (failed_at keeps the last failure).
   - A `note` is also stored in the audit row's `after` (e.g. the failure reason on MARK_FAILED).

Side effects that belong to OTHER modules (call them from the endpoint/service, not from here):
   - SUBMIT of a regular run locks the period's timesheets (services.timesheets.lock_for_period), and
     RETURN_TO_DRAFT unlocks them (A-04 wires this).
   - APPROVE is followed by START_PROCESSING + payments.submit_payout (A-05).
   - MARK_PAID creates Paystub rows, and for FINAL runs flips the membership to FORMER (A-05, A-08).
"""

import uuid
from datetime import datetime

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app import audit, clock
from app.auth.deps import STAFF, Actor
from app.errors import Conflict, Forbidden, NotFound
from app.models import PayPeriod, PayrollItem, PayrollRun
from app.models.enums import Role, RunType
from app.payroll.states import TRANSITIONS, ActorKind, RunAction, actions_from

# Plain-language past tense for error messages ("... so it can't be approved").
_DONE = {
    RunAction.SUBMIT: "submitted",
    RunAction.RETURN_TO_DRAFT: "returned to draft",
    RunAction.CANCEL: "cancelled",
    RunAction.APPROVE: "approved",
    RunAction.START_PROCESSING: "sent for payment",
    RunAction.MARK_PAID: "marked paid",
    RunAction.MARK_FAILED: "marked failed",
    RunAction.RETRY: "retried",
}
# "Only an Admin can <verb> a payroll run." (human actions only)
_VERB = {
    RunAction.SUBMIT: "submit",
    RunAction.RETURN_TO_DRAFT: "return",
    RunAction.CANCEL: "cancel",
    RunAction.APPROVE: "approve",
    RunAction.RETRY: "retry",
}


def transition(
    db: Session,
    run_id: uuid.UUID,
    action: RunAction,
    *,
    actor: Actor | None,
    note: str | None = None,
) -> PayrollRun:
    action = RunAction(action)

    # 1. Lock the row. populate_existing: if the run is already in this session, take the state
    #    we just read under the lock, not a stale copy from before another transaction committed.
    #    Flush first (the app's sessions don't autoflush) so the caller's unsaved edits to the run
    #    are written, not overwritten by that re-read, and the item check below sees new items.
    db.flush()
    run = db.execute(
        select(PayrollRun)
        .where(PayrollRun.id == run_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if run is None or (actor is not None and run.company_id != actor.company_id):
        raise NotFound("Payroll run not found.")

    # 2. The table.
    hit = TRANSITIONS.get((run.state, action))
    if hit is None:
        raise Conflict(
            f"This payroll run is {run.state.value}, so it can't be {_DONE[action]}.",
            code="illegal_transition",
            state=run.state.value,
            action=action.value,
        )
    new_state, who = hit

    # 3. Who.
    forbidden = _actor_error(who, action, actor)
    if forbidden:
        raise forbidden

    # 4. Guards.
    conflict = _guard_error(db, run, action, actor)
    if conflict:
        raise conflict

    # 5. State + columns.
    old_state = run.state
    _stamp(run, action, actor, clock.now(), note)
    run.state = new_state

    # 6. Audit, same transaction.
    after: dict[str, object] = {"state": new_state.value, "action": action.value}
    if note is not None:
        after["note"] = note
    audit.record(
        db,
        actor=actor,
        action=audit.RUN_TRANSITIONED,
        entity_type="payroll_run",
        entity_id=run.id,
        before={"state": old_state.value},
        after=after,
        company_id=run.company_id,
    )

    # 7. No commit. Flush so a later query in this transaction sees the new state.
    db.flush()
    return run


def allowed_actions_for(db: Session, run: PayrollRun, actor: Actor) -> list[RunAction]:
    if run.company_id != actor.company_id:
        return []
    allowed = []
    for action in actions_from(run.state):
        _, who = TRANSITIONS[(run.state, action)]
        if who == "system":
            continue
        if _actor_error(who, action, actor) or _guard_error(db, run, action, actor):
            continue
        allowed.append(action)
    return allowed


def _actor_error(who: ActorKind, action: RunAction, actor: Actor | None) -> Forbidden | None:
    if who == "system":
        if actor is not None:
            return Forbidden("This step happens automatically. It can't be done by hand.")
        return None
    if actor is None:
        return Forbidden("Someone has to be signed in to do that.")
    if actor.is_former:
        return Forbidden("Former employees have read-only access to their own documents.")
    if who == "admin" and actor.role != Role.ADMIN:
        return Forbidden(f"Only an Admin can {_VERB[action]} a payroll run.")
    if who == "staff" and actor.role not in STAFF:
        return Forbidden("Only an Admin or a Payroll Manager can do that.")
    return None


def _guard_error(
    db: Session, run: PayrollRun, action: RunAction, actor: Actor | None
) -> Conflict | None:
    if action == RunAction.SUBMIT:
        has_items = db.scalar(select(exists().where(PayrollItem.run_id == run.id)))
        if not has_items:
            return Conflict(
                "This run has no one to pay yet, so it can't be submitted.", code="empty_run"
            )

    if action == RunAction.APPROVE:
        if actor is not None and actor.membership_id == run.submitted_by_membership_id:
            return Conflict(
                "You submitted this run, so a different Admin has to approve it.",
                code="separation_of_duties",
            )
        if run.run_type == RunType.REGULAR:
            period = db.get(PayPeriod, run.pay_period_id)
            if period is not None and clock.now() >= period.cutoff_at:
                return Conflict(
                    "The approval deadline for this pay period has passed.",
                    code="past_cutoff",
                    cutoff_at=period.cutoff_at.isoformat(),
                )
    return None


def _stamp(
    run: PayrollRun, action: RunAction, actor: Actor | None, now: datetime, note: str | None
) -> None:
    member = actor.membership_id if actor else None
    match action:
        case RunAction.SUBMIT:
            run.submitted_at = now
            run.submitted_by_membership_id = member
        case RunAction.RETURN_TO_DRAFT:
            run.submitted_at = None
            run.submitted_by_membership_id = None
        case RunAction.CANCEL:
            run.cancelled_at = now
            run.cancelled_by_membership_id = member
        case RunAction.APPROVE:
            run.approved_at = now
            run.approved_by_membership_id = member
        case RunAction.START_PROCESSING:
            run.processing_at = now
        case RunAction.MARK_PAID:
            run.paid_at = now
        case RunAction.MARK_FAILED:
            run.failed_at = now
            run.failure_reason = note
        case RunAction.RETRY:
            run.processing_at = now
            run.failure_reason = None
