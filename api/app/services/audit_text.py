"""Plain-language audit sentences (AUD-1, AUD-2). Task B-08.

`summarize(entry, names)` returns one readable sentence per action constant in app/audit.py.
Unknown actions get a generic sentence, so a new constant never breaks the audit page.

`names` is a plain dict the router fills in (no database access here):
- "actor":  who did it (a person's name, or an email). Missing means the system did it.
- "entity": a label for the thing changed (an employee's name, a person's name for member
            entries). Optional.
- "pay_date": e.g. "Dec 11", for entries about a payroll run. Optional.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date
from typing import Any

from app import audit
from app.models import AuditLog


def format_date(d: date) -> str:
    """'Dec 11' (no zero padding, no year)."""
    return f"{d:%b} {d.day}"


def _run_label(names: Mapping[str, Any]) -> str:
    return f"payroll for {names['pay_date']}" if names.get("pay_date") else "a payroll run"


def _transitioned(entry: AuditLog, names: Mapping[str, Any]) -> str:
    after = entry.after if isinstance(entry.after, dict) else {}
    action = after.get("action")
    state = after.get("state")
    run = _run_label(names)
    verbs = {
        "submit": f"submitted {run}",
        "approve": f"approved {run}",
        "cancel": f"cancelled {run}",
        "retry": f"retried {run}",
        "start_processing": f"started sending {run}",
        "mark_paid": f"marked {run} as paid",
        "mark_failed": f"marked {run} as failed",
    }
    if action in verbs:
        return verbs[action]
    return f"moved {run} to {state}" if state else f"changed the status of {run}"


def _who(names: Mapping[str, Any]) -> str:
    return names.get("entity") or "someone"


# Each renderer returns the sentence WITHOUT the actor; summarize() prefixes the actor.
_VERBS: dict[str, Callable[[AuditLog, Mapping[str, Any]], str]] = {
    audit.COMPANY_CREATED: lambda e, n: "created the company",
    audit.COMPANY_UPDATED: lambda e, n: "updated the company details",
    audit.FUNDING_ACCOUNT_CONNECTED: lambda e, n: "connected the company funding account",
    audit.PAY_SCHEDULE_SET: lambda e, n: "set the pay schedule",
    audit.MEMBER_INVITED: lambda e, n: f"invited {_who(n)} to Forte",
    audit.MEMBER_ROLE_CHANGED: lambda e, n: f"changed the role of {_who(n)}",
    audit.MEMBER_REMOVED: lambda e, n: f"removed {_who(n)} from the company",
    audit.USER_SIGNED_IN: lambda e, n: "signed in",
    audit.EMPLOYEE_CREATED: lambda e, n: f"added {_who(n)} as an employee",
    audit.EMPLOYEE_UPDATED: lambda e, n: f"updated the record for {_who(n)}",
    audit.EMPLOYEE_PERSONAL_INFO_SET: lambda e, n: f"saved personal information for {_who(n)}",
    audit.EMPLOYEE_TERMINATED: lambda e, n: f"ended employment for {_who(n)}",
    audit.COMPENSATION_SET: lambda e, n: f"changed the pay rate for {_who(n)}",
    audit.WITHHOLDING_SET: lambda e, n: f"changed tax withholding for {_who(n)}",
    audit.BANK_ACCOUNT_SET: lambda e, n: f"changed the bank account for {_who(n)}",
    audit.SENSITIVE_FIELD_REVEALED: lambda e, n: f"viewed a protected field for {_who(n)}",
    audit.TIMESHEET_APPROVED: lambda e, n: f"approved a timesheet for {_who(n)}",
    audit.TIMESHEET_REJECTED: lambda e, n: f"rejected a timesheet for {_who(n)}",
    audit.TIMESHEETS_LOCKED: lambda e, n: "locked timesheets for the pay period",
    audit.RUN_CREATED: lambda e, n: f"created {_run_label(n)}",
    audit.RUN_RECALCULATED: lambda e, n: f"recalculated {_run_label(n)}",
    audit.RUN_TRANSITIONED: _transitioned,
    audit.CORRECTION_OPENED: lambda e, n: f"opened a correction for {_who(n)}",
}


def summarize(entry: AuditLog, names: Mapping[str, Any]) -> str:
    actor = names.get("actor") or "Forte"
    render = _VERBS.get(entry.action)
    if render is None:
        what = entry.action.replace("_", " ").replace(".", " ")
        return f"{actor} made a change ({what})."
    return f"{actor} {render(entry, names)}."
