"""Company setup (CO-1..3, Journey 1). Task B-03.

Pay periods (CO-3), biweekly only. For k = 0..5 from first_pay_date P (a weekday):
    pay_date   = P + 14k days
    end_date   = pay_date - 5 days
    start_date = end_date - 13 days
    cutoff_at  = (pay_date minus cutoff_lead_days BUSINESS days) at 17:00 America/Los_Angeles, in UTC
Generate on PUT /pay-schedule (replace periods that have no runs yet), and top up so there are always
6 future periods (do it lazily in GET /pay-periods).
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.adapters import get_bank_verifier
from app.adapters.bank import BankVerifier
from app.auth.deps import Actor, SessionUser, get_session_user, require_admin, require_staff
from app.db import get_db
from app.errors import todo
from app.schemas.common import BankAccountIn, BankAccountOut, PayPeriodOut
from app.schemas.company import CompanyCreate, CompanyOut, CompanyUpdate, PayScheduleIn

router = APIRouter(prefix="/api", tags=["company"])


@router.post("/companies", response_model=CompanyOut, status_code=status.HTTP_201_CREATED)
def create_company(
    body: CompanyCreate,
    user: SessionUser = Depends(get_session_user),
    db: Session = Depends(get_db),
):
    """Caller must have no membership yet. Creates Company + ACTIVE ADMIN membership. EIN is stored
    encrypted with ein_last4. Audit COMPANY_CREATED."""
    todo("B-03")


@router.get("/company", response_model=CompanyOut)
def get_company(actor: Actor = Depends(require_staff), db: Session = Depends(get_db)):
    todo("B-03")


@router.patch("/company", response_model=CompanyOut)
def update_company(
    body: CompanyUpdate, actor: Actor = Depends(require_admin), db: Session = Depends(get_db)
):
    todo("B-03")


@router.put("/company/funding-account", response_model=BankAccountOut)
def set_funding_account(
    body: BankAccountIn,
    actor: Actor = Depends(require_admin),
    db: Session = Depends(get_db),
    verifier: BankVerifier = Depends(get_bank_verifier),
):
    """CO-2. Verify via BankVerifier; on success mark the previous company account REPLACED.
    On failure return 422 code "bank_verification_failed" with the verifier's reason."""
    todo("B-03")


@router.put("/company/pay-schedule", response_model=list[PayPeriodOut])
def set_pay_schedule(
    body: PayScheduleIn, actor: Actor = Depends(require_admin), db: Session = Depends(get_db)
):
    todo("B-03")


@router.get("/pay-periods", response_model=list[PayPeriodOut])
def list_pay_periods(actor: Actor = Depends(require_staff), db: Session = Depends(get_db)):
    """Upcoming + recent periods, newest pay_date last, with each period's regular run id/state."""
    todo("B-03")
