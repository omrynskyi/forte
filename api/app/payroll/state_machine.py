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

Side effects that belong to OTHER modules (call them from the endpoint/service, not from here):
   - SUBMIT of a regular run locks the period's timesheets (services.timesheets.lock_for_period), and
     RETURN_TO_DRAFT unlocks them (A-04 wires this).
   - APPROVE is followed by START_PROCESSING + payments.submit_payout (A-05).
   - MARK_PAID creates Paystub rows, and for FINAL runs flips the membership to FORMER (A-05, A-08).
"""

import uuid

from sqlalchemy.orm import Session

from app.auth.deps import Actor
from app.errors import todo
from app.models import PayrollRun
from app.payroll.states import RunAction


def transition(
    db: Session,
    run_id: uuid.UUID,
    action: RunAction,
    *,
    actor: Actor | None,
    note: str | None = None,
) -> PayrollRun:
    todo("A-02")
