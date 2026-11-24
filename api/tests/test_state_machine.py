"""transition() and allowed_actions_for() (A-02, D7, D20, NFR-4, NFR-10)."""

import itertools
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import event, func, select

from app import clock
from app.errors import Conflict, Forbidden, NotFound
from app.models import AuditLog, PayrollRun
from app.models.enums import MembershipStatus, Role, RunState, RunType
from app.payroll.state_machine import allowed_actions_for, transition
from app.payroll.states import TRANSITIONS, RunAction
from tests import factories as f

S, A = RunState, RunAction
FIXED_NOW = datetime(2026, 12, 7, 18, 0, tzinfo=UTC)

# The column each action stamps with clock.now().
STAMPED = {
    A.SUBMIT: "submitted_at",
    A.CANCEL: "cancelled_at",
    A.APPROVE: "approved_at",
    A.START_PROCESSING: "processing_at",
    A.MARK_PAID: "paid_at",
    A.MARK_FAILED: "failed_at",
    A.RETRY: "processing_at",
}


@pytest.fixture
def frozen(monkeypatch):
    monkeypatch.setattr(clock, "now", lambda: FIXED_NOW)
    return FIXED_NOW


@pytest.fixture
def team(db):
    """A company with two Admins, a Payroll Manager, an employee member, and one paid employee."""
    company = f.make_company(db)
    emp = f.make_employee(db, company)
    return {
        "company": company,
        "emp": emp,
        "admin": f.make_member(db, company, Role.ADMIN),
        "admin2": f.make_member(db, company, Role.ADMIN),
        "pm": f.make_member(db, company, Role.PAYROLL_MANAGER),
        "employee": f.make_member(db, company, Role.EMPLOYEE, employee=emp),
    }


_n = itertools.count(1)


def _run(db, team, state=S.DRAFT, *, cutoff_at=None, **kw):
    """A run in `state` with one item for the team's employee. Regular runs get their own period
    with a cutoff 3 h after FIXED_NOW."""
    period = None
    if kw.get("run_type", RunType.REGULAR) == RunType.REGULAR:
        period = f.make_pay_period(
            db,
            team["company"],
            date(2026, 12, 11) + timedelta(weeks=2 * next(_n)),
            cutoff_at=cutoff_at or FIXED_NOW + timedelta(hours=3),
        )
    kw.setdefault("employees", [team["emp"]])
    return f.make_run(db, team["company"], state=state, period=period, **kw)


def _audit_count(db, run):
    return db.scalar(
        select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == str(run.id))
    )


def _actor_for(db, team, who):
    if who == "system":
        return None
    member = team["admin2"] if who == "admin" else team["pm"]
    return f.actor_for(db, member)


# --- every legal transition ---------------------------------------------------------------


@pytest.mark.parametrize(("state", "action"), list(TRANSITIONS))
def test_every_legal_transition(db, team, frozen, state, action):
    new_state, who = TRANSITIONS[(state, action)]
    # Submitted by the PM, so admin2 may approve (D20).
    run = _run(db, team, state, submitted_by=team["pm"] if state == S.SUBMITTED else None)
    actor = _actor_for(db, team, who)
    note = "Bank rejected the payout" if action == A.MARK_FAILED else None

    out = transition(db, run.id, action, actor=actor, note=note)

    assert out.state == new_state
    db.expire_all()
    stored = db.get(PayrollRun, run.id)
    assert stored.state == new_state
    if action in STAMPED:
        assert getattr(stored, STAMPED[action]) == frozen
    entry = db.scalars(select(AuditLog).where(AuditLog.entity_id == str(run.id))).one()
    assert entry.action == "run.transitioned"
    assert entry.entity_type == "payroll_run"
    assert entry.company_id == team["company"].id
    assert entry.before == {"state": state.value}
    assert entry.after["state"] == new_state.value
    assert entry.after["action"] == action.value
    if actor is None:
        assert entry.actor_membership_id is None
    else:
        assert entry.actor_membership_id == actor.membership_id


def test_by_columns_record_who(db, team, frozen):
    run = _run(db, team)
    pm, admin = f.actor_for(db, team["pm"]), f.actor_for(db, team["admin"])
    transition(db, run.id, A.SUBMIT, actor=pm)
    assert run.submitted_by_membership_id == pm.membership_id
    transition(db, run.id, A.APPROVE, actor=admin)
    assert run.approved_by_membership_id == admin.membership_id

    other = _run(db, team)
    transition(db, other.id, A.CANCEL, actor=admin)
    assert other.cancelled_by_membership_id == admin.membership_id


def test_mark_failed_stores_reason_and_retry_clears_it(db, team, frozen):
    run = _run(db, team, S.PROCESSING)
    transition(db, run.id, A.MARK_FAILED, actor=None, note="Account closed")
    assert run.failure_reason == "Account closed"
    assert run.failed_at == frozen

    transition(db, run.id, A.RETRY, actor=f.actor_for(db, team["admin"]))
    assert run.state == S.PROCESSING
    assert run.failure_reason is None
    assert run.failed_at == frozen  # the last failure is still on record
    failed = db.scalars(
        select(AuditLog).where(AuditLog.entity_id == str(run.id)).order_by(AuditLog.id)
    ).first()
    assert failed.after["note"] == "Account closed"


def test_return_to_draft_clears_submitter(db, team, frozen):
    run = _run(db, team, S.SUBMITTED, submitted_by=team["pm"])
    transition(db, run.id, A.RETURN_TO_DRAFT, actor=f.actor_for(db, team["admin"]))
    assert run.state == S.DRAFT
    assert run.submitted_at is None
    assert run.submitted_by_membership_id is None


def test_full_happy_path(db, team, frozen):
    run = _run(db, team)
    pm, admin = f.actor_for(db, team["pm"]), f.actor_for(db, team["admin"])
    transition(db, run.id, A.SUBMIT, actor=pm)
    transition(db, run.id, A.APPROVE, actor=admin)
    transition(db, run.id, A.START_PROCESSING, actor=None)
    transition(db, run.id, A.MARK_PAID, actor=None)
    assert run.state == S.PAID
    assert _audit_count(db, run) == 4


# --- every illegal (state, action) pair ---------------------------------------------------


def test_every_illegal_pair_is_rejected(db, team):
    admin = f.actor_for(db, team["admin"])
    runs = {s: _run(db, team, s, run_type=RunType.CORRECTION) for s in RunState}
    illegal = [
        (s, a) for s, a in itertools.product(RunState, RunAction) if (s, a) not in TRANSITIONS
    ]
    assert len(illegal) == len(RunState) * len(RunAction) - len(TRANSITIONS)
    for state, action in illegal:
        for actor in (admin, None):
            with pytest.raises(Conflict) as err:
                transition(db, runs[state].id, action, actor=actor)
            assert err.value.code == "illegal_transition", (state, action)
            assert err.value.status_code == 409
            assert runs[state].state == state
    for run in runs.values():
        assert _audit_count(db, run) == 0


# --- who may fire what --------------------------------------------------------------------


def test_pm_cannot_approve_or_cancel(db, team):
    pm = f.actor_for(db, team["pm"])
    submitted = _run(db, team, S.SUBMITTED, submitted_by=team["admin"])
    draft = _run(db, team)
    for run, action in ((submitted, A.APPROVE), (submitted, A.CANCEL), (draft, A.CANCEL)):
        with pytest.raises(Forbidden) as err:
            transition(db, run.id, action, actor=pm)
        assert err.value.status_code == 403
    failed = _run(db, team, S.FAILED)
    with pytest.raises(Forbidden):
        transition(db, failed.id, A.RETRY, actor=pm)


def test_employee_cannot_fire_any_human_action(db, team):
    employee = f.actor_for(db, team["employee"])
    draft = _run(db, team)
    with pytest.raises(Forbidden):
        transition(db, draft.id, A.SUBMIT, actor=employee)
    with pytest.raises(Forbidden):
        transition(db, draft.id, A.CANCEL, actor=employee)


def test_former_member_is_rejected(db, team):
    former = f.make_member(db, team["company"], Role.ADMIN, status=MembershipStatus.FORMER)
    run = _run(db, team)
    with pytest.raises(Forbidden):
        transition(db, run.id, A.SUBMIT, actor=f.actor_for(db, former))


def test_system_actions_reject_a_human(db, team):
    admin = f.actor_for(db, team["admin"])
    for state, action in (
        (S.APPROVED, A.START_PROCESSING),
        (S.PROCESSING, A.MARK_PAID),
        (S.PROCESSING, A.MARK_FAILED),
    ):
        run = _run(db, team, state)
        with pytest.raises(Forbidden):
            transition(db, run.id, action, actor=admin)
        assert run.state == state


def test_human_actions_reject_no_actor(db, team):
    for state, action in (
        (S.DRAFT, A.SUBMIT),
        (S.SUBMITTED, A.RETURN_TO_DRAFT),
        (S.DRAFT, A.CANCEL),
        (S.SUBMITTED, A.APPROVE),
        (S.FAILED, A.RETRY),
    ):
        run = _run(db, team, state, submitted_by=team["pm"] if state == S.SUBMITTED else None)
        with pytest.raises(Forbidden):
            transition(db, run.id, action, actor=None)
        assert run.state == state


# --- guards -------------------------------------------------------------------------------


def test_submit_empty_run(db, team):
    run = _run(db, team, employees=[])
    with pytest.raises(Conflict) as err:
        transition(db, run.id, A.SUBMIT, actor=f.actor_for(db, team["pm"]))
    assert err.value.code == "empty_run"
    assert run.state == S.DRAFT


def test_submitter_cannot_approve(db, team, frozen):
    """D20: the Admin who submitted can't approve, even though they're an Admin."""
    run = _run(db, team, S.SUBMITTED, submitted_by=team["admin"])
    with pytest.raises(Conflict) as err:
        transition(db, run.id, A.APPROVE, actor=f.actor_for(db, team["admin"]))
    assert err.value.code == "separation_of_duties"
    assert run.state == S.SUBMITTED
    transition(db, run.id, A.APPROVE, actor=f.actor_for(db, team["admin2"]))
    assert run.state == S.APPROVED


def test_approve_after_cutoff(db, team, monkeypatch):
    cutoff = FIXED_NOW + timedelta(hours=3)
    run = _run(db, team, S.SUBMITTED, submitted_by=team["pm"], cutoff_at=cutoff)
    admin = f.actor_for(db, team["admin"])

    monkeypatch.setattr(clock, "now", lambda: cutoff)  # exactly at the cutoff is too late
    with pytest.raises(Conflict) as err:
        transition(db, run.id, A.APPROVE, actor=admin)
    assert err.value.code == "past_cutoff"
    assert "cutoff_at" in err.value.extra

    monkeypatch.setattr(clock, "now", lambda: cutoff - timedelta(seconds=1))
    transition(db, run.id, A.APPROVE, actor=admin)
    assert run.state == S.APPROVED


def test_cutoff_does_not_apply_to_off_cycle_runs(db, team, monkeypatch):
    monkeypatch.setattr(clock, "now", lambda: datetime(2030, 1, 1, tzinfo=UTC))
    for run_type in (RunType.CORRECTION, RunType.FINAL, RunType.BONUS):
        run = _run(db, team, S.SUBMITTED, run_type=run_type, submitted_by=team["pm"])
        transition(db, run.id, A.APPROVE, actor=f.actor_for(db, team["admin"]))
        assert run.state == S.APPROVED


def test_failures_write_no_audit(db, team, frozen):
    run = _run(db, team, S.SUBMITTED, submitted_by=team["admin"])
    admin, pm = f.actor_for(db, team["admin"]), f.actor_for(db, team["pm"])
    for action, actor in ((A.APPROVE, admin), (A.APPROVE, pm), (A.SUBMIT, admin)):
        with pytest.raises((Conflict, Forbidden)):
            transition(db, run.id, action, actor=actor)
    assert _audit_count(db, run) == 0


# --- tenant isolation and locking ---------------------------------------------------------


def test_other_tenant_gets_not_found(db, team):
    run = _run(db, team)
    _, outsider = f.other_company_setup(db)
    with pytest.raises(NotFound) as err:
        transition(db, run.id, A.SUBMIT, actor=f.actor_for(db, outsider))
    assert err.value.status_code == 404
    assert run.state == S.DRAFT
    assert _audit_count(db, run) == 0


def test_unknown_run_is_not_found(db, team):
    with pytest.raises(NotFound):
        transition(db, uuid.uuid4(), A.SUBMIT, actor=f.actor_for(db, team["admin"]))


def test_locks_the_row(db, team):
    run = _run(db, team)
    seen: list[str] = []

    def capture(conn, cursor, statement, *args):
        seen.append(statement)

    bind = db.connection()
    event.listen(bind, "before_cursor_execute", capture)
    try:
        transition(db, run.id, A.SUBMIT, actor=f.actor_for(db, team["pm"]))
    finally:
        event.remove(bind, "before_cursor_execute", capture)
    assert any("FROM payroll_runs" in s and "FOR UPDATE" in s for s in seen)


def test_reads_fresh_state_under_the_lock(db, team):
    """The run is already loaded in the session; transition() must not trust that copy."""
    run = _run(db, team)
    db.execute(
        PayrollRun.__table__.update().where(PayrollRun.id == run.id).values(state=S.CANCELLED.value)
    )
    with pytest.raises(Conflict) as err:
        transition(db, run.id, A.SUBMIT, actor=f.actor_for(db, team["pm"]))
    assert err.value.code == "illegal_transition"


def test_keeps_callers_unflushed_changes(db, team):
    """The app's sessions don't autoflush. An edit the caller made to the run (A-05 sets
    provider_payout_id) must survive the locked re-read."""
    run = _run(db, team, S.PROCESSING)
    with db.no_autoflush:
        run.provider_payout_id = "po_test_1"
        transition(db, run.id, A.MARK_PAID, actor=None)
    db.expire_all()
    stored = db.get(PayrollRun, run.id)
    assert stored.provider_payout_id == "po_test_1"
    assert stored.state == S.PAID


def test_does_not_commit(db, team):
    run = _run(db, team)
    commits: list[bool] = []
    event.listen(db, "after_commit", lambda _s: commits.append(True))
    transition(db, run.id, A.SUBMIT, actor=f.actor_for(db, team["pm"]))
    assert commits == []


# --- allowed_actions_for ------------------------------------------------------------------


def test_allowed_actions_by_role(db, team, frozen):
    admin, pm = f.actor_for(db, team["admin"]), f.actor_for(db, team["pm"])
    employee = f.actor_for(db, team["employee"])

    draft = _run(db, team)
    assert allowed_actions_for(db, draft, admin) == [A.SUBMIT, A.CANCEL]
    assert allowed_actions_for(db, draft, pm) == [A.SUBMIT]
    assert allowed_actions_for(db, draft, employee) == []

    submitted = _run(db, team, S.SUBMITTED, submitted_by=team["pm"])
    assert set(allowed_actions_for(db, submitted, admin)) == {
        A.RETURN_TO_DRAFT,
        A.CANCEL,
        A.APPROVE,
    }
    assert allowed_actions_for(db, submitted, pm) == [A.RETURN_TO_DRAFT]

    failed = _run(db, team, S.FAILED)
    assert allowed_actions_for(db, failed, admin) == [A.RETRY]
    assert allowed_actions_for(db, failed, pm) == []


def test_allowed_actions_never_include_system_actions(db, team):
    admin = f.actor_for(db, team["admin"])
    for state in (S.APPROVED, S.PROCESSING, S.PAID, S.CANCELLED):
        assert allowed_actions_for(db, _run(db, team, state), admin) == []


def test_allowed_actions_hide_approve_from_the_submitter(db, team, frozen):
    run = _run(db, team, S.SUBMITTED, submitted_by=team["admin"])
    assert A.APPROVE not in allowed_actions_for(db, run, f.actor_for(db, team["admin"]))
    assert A.APPROVE in allowed_actions_for(db, run, f.actor_for(db, team["admin2"]))


def test_allowed_actions_hide_approve_after_cutoff(db, team, monkeypatch):
    cutoff = FIXED_NOW + timedelta(hours=3)
    run = _run(db, team, S.SUBMITTED, submitted_by=team["pm"], cutoff_at=cutoff)
    admin = f.actor_for(db, team["admin"])
    monkeypatch.setattr(clock, "now", lambda: cutoff - timedelta(minutes=1))
    assert A.APPROVE in allowed_actions_for(db, run, admin)
    monkeypatch.setattr(clock, "now", lambda: cutoff + timedelta(minutes=1))
    assert A.APPROVE not in allowed_actions_for(db, run, admin)


def test_allowed_actions_hide_submit_for_an_empty_run(db, team):
    run = _run(db, team, employees=[])
    assert allowed_actions_for(db, run, f.actor_for(db, team["admin"])) == [A.CANCEL]


def test_allowed_actions_for_other_tenant_is_empty(db, team):
    _, outsider = f.other_company_setup(db)
    assert allowed_actions_for(db, _run(db, team), f.actor_for(db, outsider)) == []


@pytest.mark.parametrize(
    ("state", "action"), [k for k, v in TRANSITIONS.items() if v[1] != "system"]
)
def test_allowed_actions_match_transition(db, team, frozen, state, action):
    """Every action offered must succeed, and every action refused must fail."""
    for member in ("admin", "admin2", "pm", "employee"):
        run = _run(db, team, state, submitted_by=team["admin"] if state == S.SUBMITTED else None)
        actor = f.actor_for(db, team[member])
        offered = action in allowed_actions_for(db, run, actor)
        try:
            transition(db, run.id, action, actor=actor)
            succeeded = True
        except (Conflict, Forbidden):
            succeeded = False
        assert offered == succeeded, (state, action, member)
