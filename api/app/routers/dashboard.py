"""Admin home (RUN-6, Journey 3 step 6). Task A-09.

- next_period: earliest pay period whose regular run is not PAID/PROCESSING/APPROVED.
- at_risk: now >= cutoff_at and the current run isn't APPROVED or later (or doesn't exist).
- recent_activity: last 5 audit entries rendered with B-08's summarize(); PMs see only their own.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.deps import Actor, require_staff
from app.db import get_db
from app.errors import todo
from app.schemas.dashboard import DashboardOut

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(actor: Actor = Depends(require_staff), db: Session = Depends(get_db)):
    todo("A-09")
