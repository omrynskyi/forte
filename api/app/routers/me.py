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

from datetime import timedelta

from fastapi import APIRouter, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import audit, clock
from app.adapters import get_bank_verifier
from app.adapters.bank import BankVerifier
from app.auth.deps import Actor, require_employee_self
from app.auth.scoping import get_scoped, scoped
from app.db import get_db
from app.errors import AppError
from app.models import BankAccount, Company, Employee, Withholding
from app.models.enums import BankAccountStatus, BankOwnerType
from app.schemas.common import AddressOut, BankAccountIn, BankAccountOut
from app.schemas.me import PersonalInfoIn, ProfileOut, WithholdingIn, WithholdingOut
from app.security.crypto import last4


class PrivateValidationRoute(APIRoute):
    """Don't echo SSNs or bank numbers in FastAPI's validation-error input fields."""

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def private_handler(request):
            try:
                response = await handler(request)
                response.headers["Cache-Control"] = "no-store"
                return response
            except RequestValidationError as exc:
                # Keep locations/messages, but omit submitted values and validation context.
                errors = [
                    {key: value for key, value in error.items() if key in {"type", "loc", "msg"}}
                    for error in exc.errors()
                ]
                return JSONResponse(
                    status_code=422,
                    content={"detail": errors},
                    headers={"Cache-Control": "no-store"},
                )

        return private_handler


router = APIRouter(prefix="/api/me", tags=["me"], route_class=PrivateValidationRoute)


@router.get("/profile", response_model=ProfileOut)
def get_profile(
    actor: Actor = Depends(require_employee_self(allow_former=True)),
    db: Session = Depends(get_db),
):
    return _profile(db, _employee(db, actor), actor)


@router.put("/personal", response_model=ProfileOut)
def set_personal_info(
    body: PersonalInfoIn,
    actor: Actor = Depends(require_employee_self()),
    db: Session = Depends(get_db),
):
    ssn = body.ssn.replace("-", "")
    if len(ssn) != 9 or not ssn.isascii() or not ssn.isdigit():
        raise SelfServiceValidationError("Enter a nine-digit SSN.", code="invalid_ssn")
    if body.dob > clock.today_pacific():
        raise SelfServiceValidationError(
            "Date of birth cannot be in the future.", code="invalid_dob"
        )
    employee = _employee(db, actor, lock=True)
    before = _personal_snapshot(employee)
    employee.first_name = body.first_name
    employee.last_name = body.last_name
    employee.dob = body.dob
    employee.ssn = ssn
    employee.ssn_last4 = last4(ssn)
    employee.address_line1 = body.address.line1
    employee.address_line2 = body.address.line2
    employee.city = body.address.city
    employee.state = body.address.state
    employee.zip = body.address.zip
    audit.record(
        db,
        actor=actor,
        action=audit.EMPLOYEE_PERSONAL_INFO_SET,
        entity_type="employee",
        entity_id=employee.id,
        before=before,
        after=_personal_snapshot(employee),
    )
    db.flush()
    return _profile(db, employee, actor)


@router.put("/withholding", response_model=WithholdingOut)
def set_withholding(
    body: WithholdingIn,
    actor: Actor = Depends(require_employee_self()),
    db: Session = Depends(get_db),
):
    employee = _employee(db, actor, lock=True)
    previous = _withholding(db, actor)
    today = clock.today_pacific()
    created_at = clock.now()
    # Two edits can share a clock tick. Preserve deterministic "latest version" ordering
    # for readiness and the payroll engine without modifying any historical row.
    if previous and previous.effective_date == today and previous.created_at >= created_at:
        created_at = previous.created_at + timedelta(microseconds=1)
    withholding = Withholding(
        company_id=actor.company_id,
        employee_id=employee.id,
        effective_date=today,
        created_at=created_at,
        created_by_membership_id=actor.membership_id,
        **body.model_dump(),
    )
    db.add(withholding)
    db.flush()
    result = WithholdingOut.model_validate(withholding)
    audit.record(
        db,
        actor=actor,
        action=audit.WITHHOLDING_SET,
        entity_type="withholding",
        entity_id=withholding.id,
        before=WithholdingOut.model_validate(previous).model_dump(mode="json")
        if previous
        else None,
        after=result.model_dump(mode="json"),
    )
    return result


@router.put("/bank-account", response_model=BankAccountOut)
def set_bank_account(
    body: BankAccountIn,
    actor: Actor = Depends(require_employee_self()),
    db: Session = Depends(get_db),
    verifier: BankVerifier = Depends(get_bank_verifier),
):
    employee = _employee(db, actor, lock=True)
    verification = verifier.verify(body.routing_number, body.account_number)
    if verification.status != "verified":
        raise SelfServiceValidationError(
            verification.reason or "The bank could not verify this account.",
            code="bank_verification_failed",
            reason=verification.reason,
        )
    previous = _deposit(db, actor)
    db.execute(
        scoped(update(BankAccount), BankAccount, actor)
        .where(
            BankAccount.employee_id == employee.id,
            BankAccount.owner_type == BankOwnerType.EMPLOYEE,
            BankAccount.status != BankAccountStatus.REPLACED,
        )
        .values(status=BankAccountStatus.REPLACED)
    )
    account = BankAccount(
        company_id=actor.company_id,
        employee_id=employee.id,
        owner_type=BankOwnerType.EMPLOYEE,
        routing_number=body.routing_number,
        account_number=body.account_number,
        account_last4=last4(body.account_number),
        account_type=body.account_type,
        status=BankAccountStatus.VERIFIED,
        verified_at=clock.now(),
        provider_ref=verification.provider_ref,
    )
    db.add(account)
    db.flush()
    audit.record(
        db,
        actor=actor,
        action=audit.BANK_ACCOUNT_SET,
        entity_type="bank_account",
        entity_id=account.id,
        before={"account_last4": previous.account_last4} if previous else None,
        after={"account_last4": account.account_last4},
    )
    return BankAccountOut.model_validate(account)


def _employee(db: Session, actor: Actor, *, lock: bool = False) -> Employee:
    employee = get_scoped(db, Employee, actor.employee_id, actor)
    if lock:
        db.refresh(employee, with_for_update=True)
    return employee


def _withholding(db: Session, actor: Actor) -> Withholding | None:
    return db.scalar(
        scoped(select(Withholding), Withholding, actor)
        .where(
            Withholding.employee_id == actor.employee_id,
            Withholding.effective_date <= clock.today_pacific(),
        )
        .order_by(Withholding.effective_date.desc(), Withholding.created_at.desc())
        .limit(1)
    )


def _deposit(db: Session, actor: Actor) -> BankAccount | None:
    return db.scalar(
        scoped(select(BankAccount), BankAccount, actor)
        .where(
            BankAccount.employee_id == actor.employee_id,
            BankAccount.owner_type == BankOwnerType.EMPLOYEE,
            BankAccount.status == BankAccountStatus.VERIFIED,
        )
        .order_by(BankAccount.created_at.desc(), BankAccount.id)
        .limit(1)
    )


def _personal_snapshot(employee: Employee) -> dict:
    return {
        "first_name": employee.first_name,
        "last_name": employee.last_name,
        "dob": employee.dob.isoformat() if employee.dob else None,
        "ssn_last4": employee.ssn_last4,
        "address": {
            "line1": employee.address_line1,
            "line2": employee.address_line2,
            "city": employee.city,
            "state": employee.state,
            "zip": employee.zip,
        },
    }


def _profile(db: Session, employee: Employee, actor: Actor) -> ProfileOut:
    company = db.get(Company, actor.company_id)
    withholding = _withholding(db, actor)
    account = _deposit(db, actor)
    address = None
    if employee.address_line1 and employee.city and employee.state and employee.zip:
        address = AddressOut(**_personal_snapshot(employee)["address"])
    return ProfileOut(
        employee_id=employee.id,
        employee_number=employee.employee_number,
        first_name=employee.first_name,
        last_name=employee.last_name,
        email=employee.email,
        job_title=employee.job_title,
        company_name=company.legal_name,
        dob=employee.dob,
        ssn_last4=employee.ssn_last4,
        address=address,
        withholding=WithholdingOut.model_validate(withholding) if withholding else None,
        deposit_account=BankAccountOut.model_validate(account) if account else None,
        is_former=actor.is_former,
        end_date=employee.end_date,
    )


class SelfServiceValidationError(AppError):
    status_code = 422
    code = "invalid_employee_details"
