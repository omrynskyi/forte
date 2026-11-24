"""Timesheets (TIME-1..3). Task B-07.

Employee side (hourly employees only; salaried -> 409 "not_hourly"):
- The "open period" is the earliest pay period with start_date <= today whose regular run is not
  yet submitted (no run, or run in DRAFT/CANCELLED). Create the Timesheet lazily on GET.
- PUT entries: allowed when status OPEN or REJECTED (REJECTED -> OPEN). Dates must be inside the
  period and <= today. minutes=0 deletes the entry. LOCKED/APPROVED -> 409 "timesheet_locked".
Manager side (Admin or PM):
- approve: OPEN|REJECTED -> APPROVED. reject (note required): OPEN|APPROVED -> REJECTED.
  Audit TIMESHEET_APPROVED / TIMESHEET_REJECTED. A PM can't approve their own timesheet.
Shared services:
- lock_for_period / unlock_for_period / approved_minutes: ALREADY IMPLEMENTED in
  app/services/timesheets.py (skeleton). Reuse them; do not reimplement.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.deps import Actor, require_employee_self, require_staff
from app.db import get_db
from app.errors import todo
from app.schemas.timesheets import ReviewIn, TimesheetEntriesPut, TimesheetOut

router = APIRouter(prefix="/api", tags=["timesheets"])


@router.get("/me/timesheet", response_model=TimesheetOut)
def my_timesheet(actor: Actor = Depends(require_employee_self()), db: Session = Depends(get_db)):
    todo("B-07")


@router.put("/me/timesheet/entries", response_model=TimesheetOut)
def put_my_entries(
    body: TimesheetEntriesPut,
    actor: Actor = Depends(require_employee_self()),
    db: Session = Depends(get_db),
):
    todo("B-07")


@router.get("/timesheets", response_model=list[TimesheetOut])
def list_timesheets(
    pay_period_id: uuid.UUID | None = None,
    actor: Actor = Depends(require_staff),
    db: Session = Depends(get_db),
):
    """Defaults to the open period. One row per active hourly employee (sheet created lazily)."""
    todo("B-07")


@router.post("/timesheets/{timesheet_id}/approve", response_model=TimesheetOut)
def approve_timesheet(
    timesheet_id: uuid.UUID,
    body: ReviewIn,
    actor: Actor = Depends(require_staff),
    db: Session = Depends(get_db),
):
    todo("B-07")


@router.post("/timesheets/{timesheet_id}/reject", response_model=TimesheetOut)
def reject_timesheet(
    timesheet_id: uuid.UUID,
    body: ReviewIn,
    actor: Actor = Depends(require_staff),
    db: Session = Depends(get_db),
):
    todo("B-07")
