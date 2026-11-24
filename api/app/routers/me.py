"""Employee self-service (ONB-1, ONB-2, EMP-4). Task B-06.

- Acts only on actor.employee_id. Former employees: GET /profile only (read-only).
- PUT /personal: encrypt SSN, set ssn_last4. Audit EMPLOYEE_PERSONAL_INFO_SET (masked).
- PUT /withholding: append a new Withholding row effective today. Audit WITHHOLDING_SET.
- PUT /bank-account: verify via BankVerifier; on success mark previous employee accounts REPLACED;
  on failure 422 "bank_verification_failed". Audit BANK_ACCOUNT_SET (last4 only).
  ONB-3 hold and NOTE-1 emails are cut (D3).
- There is no endpoint that changes pay rate or job title (EMP-4).
- /api/me/home lives in routers/paystubs.py (A-06) because it is mostly paystub data.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.adapters import get_bank_verifier
from app.adapters.bank import BankVerifier
from app.auth.deps import Actor, require_employee_self
from app.db import get_db
from app.errors import todo
from app.schemas.common import BankAccountIn, BankAccountOut
from app.schemas.me import PersonalInfoIn, ProfileOut, WithholdingIn, WithholdingOut

router = APIRouter(prefix="/api/me", tags=["me"])


@router.get("/profile", response_model=ProfileOut)
def get_profile(
    actor: Actor = Depends(require_employee_self(allow_former=True)),
    db: Session = Depends(get_db),
):
    todo("B-06")


@router.put("/personal", response_model=ProfileOut)
def set_personal_info(
    body: PersonalInfoIn,
    actor: Actor = Depends(require_employee_self()),
    db: Session = Depends(get_db),
):
    todo("B-06")


@router.put("/withholding", response_model=WithholdingOut)
def set_withholding(
    body: WithholdingIn,
    actor: Actor = Depends(require_employee_self()),
    db: Session = Depends(get_db),
):
    todo("B-06")


@router.put("/bank-account", response_model=BankAccountOut)
def set_bank_account(
    body: BankAccountIn,
    actor: Actor = Depends(require_employee_self()),
    db: Session = Depends(get_db),
    verifier: BankVerifier = Depends(get_bank_verifier),
):
    todo("B-06")
