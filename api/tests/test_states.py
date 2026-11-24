"""The state machine TABLE (D7). A-02 adds tests for the transition() service on top of these."""

from app.models.enums import RunState
from app.payroll.states import (
    TERMINAL_STATES,
    TRANSITIONS,
    RunAction,
    actions_from,
    correction_status,
    next_state,
)


def test_seven_states_nine_transitions():
    assert len(RunState) == 7
    assert len(TRANSITIONS) == 9


def test_every_state_reachable_from_draft():
    seen, frontier = {RunState.DRAFT}, [RunState.DRAFT]
    while frontier:
        s = frontier.pop()
        for a in actions_from(s):
            n = next_state(s, a)
            if n and n not in seen:
                seen.add(n)
                frontier.append(n)
    assert seen == set(RunState)


def test_terminal_states_have_no_exits():
    for s in TERMINAL_STATES:
        assert actions_from(s) == []


def test_approved_run_can_never_go_back():
    for s in (RunState.APPROVED, RunState.PROCESSING, RunState.PAID, RunState.FAILED):
        assert next_state(s, RunAction.RETURN_TO_DRAFT) is None
        assert next_state(s, RunAction.CANCEL) is None


def test_only_system_moves_money_states():
    for (state, action), (_, who) in TRANSITIONS.items():
        if action in (RunAction.START_PROCESSING, RunAction.MARK_PAID, RunAction.MARK_FAILED):
            assert who == "system", (state, action)
        if action in (RunAction.APPROVE, RunAction.CANCEL):
            assert who == "admin", (state, action)  # RUN-3


def test_correction_status_covers_every_state():
    assert {correction_status(s) for s in RunState} == {
        "opened",
        "in_review",
        "approved",
        "paid",
        "cancelled",
    }
