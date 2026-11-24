from datetime import datetime

from app.schemas.audit import AuditEntryOut
from app.schemas.common import ApiModel, PayPeriodOut
from app.schemas.company import SetupChecklist
from app.schemas.runs import RunBlocker, RunSummary


class TimesheetCounts(ApiModel):
    hourly_employees: int
    approved: int
    open: int
    rejected: int


class DashboardOut(ApiModel):
    """Admin-Home (RUN-6). The client renders the countdown from cutoff_at - server_time, then ticks
    locally. Color thresholds are a UI concern (docs/ARCHITECTURE.md#countdown)."""

    company_name: str
    server_time: datetime
    next_period: PayPeriodOut | None
    current_run: RunSummary | None  # regular run for next_period, if created
    cutoff_at: datetime | None
    at_risk: bool
    timesheets: TimesheetCounts
    not_ready: list[RunBlocker]
    setup_complete: bool
    setup: SetupChecklist
    recent_activity: list[AuditEntryOut]  # latest 5 (PMs: only their own, per matrix)
