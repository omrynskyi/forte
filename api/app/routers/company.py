"""Company setup (CO-1..3, Journey 1). Task B-03.

Pay periods (CO-3), biweekly only. For k = 0..5 from first_pay_date P (a weekday):
    pay_date   = P + 14k days
    end_date   = pay_date - 5 days
    start_date = end_date - 13 days
    cutoff_at  = (pay_date minus cutoff_lead_days BUSINESS days) at 17:00 America/Los_Angeles, in UTC
Generate on PUT /pay-schedule (replace periods that have no runs yet), and top up so there are always
6 future periods (do it lazily in GET /pay-periods).
"""

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import audit, clock
from app.adapters import get_bank_verifier
from app.adapters.bank import BankVerifier
from app.auth.deps import Actor, SessionUser, get_session_user, require_admin, require_staff
from app.auth.scoping import scoped
from app.db import get_db
from app.errors import AppError, Conflict, Unauthorized
from app.models import BankAccount, Company, Membership, User
from app.models.enums import BankAccountStatus, BankOwnerType, MembershipStatus, Role
from app.schemas.common import AddressIn, AddressOut, BankAccountIn, BankAccountOut, PayPeriodOut
from app.schemas.company import (
    CompanyCreate,
    CompanyOut,
    CompanyUpdate,
    PayScheduleIn,
    SetupChecklist,
)
from app.security.crypto import last4
from app.services.pay_periods import (
    ensure_future_periods,
    list_periods,
    lock_company,
    set_schedule,
)

router = APIRouter(prefix="/api", tags=["company"])


@router.post("/companies", response_model=CompanyOut, status_code=status.HTTP_201_CREATED)
def create_company(
    body: CompanyCreate,
    request: Request,
    user: SessionUser = Depends(get_session_user),
    db: Session = Depends(get_db),
):
    """Caller must have no membership yet. Creates Company + ACTIVE ADMIN membership. EIN is stored
    encrypted with ein_last4. Audit COMPANY_CREATED."""
    ein = _normalize_ein(body.ein)
    # Bootstrap from the authenticated user; serialize concurrent company signups.
    stored_user = db.scalar(select(User).where(User.id == user.user_id).with_for_update())
    if stored_user is None:
        raise Unauthorized("Sign in to create a company.")
    if db.scalar(select(Membership.id).where(Membership.user_id == user.user_id)) is not None:
        raise Conflict("You already belong to a company.", code="already_has_company")
    company = Company(legal_name=body.legal_name, ein=ein, ein_last4=last4(body.ein))
    _set_address(company, body.address)
    db.add(company)
    db.flush()
    member = Membership(
        company_id=company.id, user_id=user.user_id, role=Role.ADMIN, status=MembershipStatus.ACTIVE
    )
    db.add(member)
    db.flush()
    actor = Actor(
        user_id=user.user_id,
        email=stored_user.email,
        membership_id=member.id,
        company_id=company.id,
        role=member.role,
        status=member.status,
        employee_id=None,
        ip=request.client.host if request.client else None,
    )
    audit.record(
        db,
        actor=actor,
        action=audit.COMPANY_CREATED,
        entity_type="company",
        entity_id=company.id,
        after=_profile(company),
    )
    return _company_out(db, company, actor)


@router.get("/company", response_model=CompanyOut)
def get_company(actor: Actor = Depends(require_staff), db: Session = Depends(get_db)):
    company = lock_company(db, actor)
    return _company_out(db, company, actor)


@router.patch("/company", response_model=CompanyOut)
def update_company(
    body: CompanyUpdate, actor: Actor = Depends(require_admin), db: Session = Depends(get_db)
):
    company = lock_company(db, actor)
    ein = _normalize_ein(body.ein) if body.ein is not None else None
    before = _profile(company)
    if body.legal_name is not None:
        company.legal_name = body.legal_name
    if body.ein is not None:
        company.ein = ein
        company.ein_last4 = last4(body.ein)
    if body.address is not None:
        _set_address(company, body.address)
    audit.record(
        db,
        actor=actor,
        action=audit.COMPANY_UPDATED,
        entity_type="company",
        entity_id=company.id,
        before=before,
        after=_profile(company),
    )
    db.flush()
    return _company_out(db, company, actor)


@router.put("/company/funding-account", response_model=BankAccountOut)
def set_funding_account(
    body: BankAccountIn,
    actor: Actor = Depends(require_admin),
    db: Session = Depends(get_db),
    verifier: BankVerifier = Depends(get_bank_verifier),
):
    """CO-2. Verify via BankVerifier; on success mark the previous company account REPLACED.
    On failure return 422 code "bank_verification_failed" with the verifier's reason."""
    company = lock_company(db, actor)
    verification = verifier.verify(body.routing_number, body.account_number)
    if verification.status != "verified":
        raise CompanyValidationError(
            verification.reason or "The bank could not verify this account.",
            code="bank_verification_failed",
            reason=verification.reason,
        )
    previous = _funding_account(db, actor)
    db.execute(
        scoped(update(BankAccount), BankAccount, actor)
        .where(
            BankAccount.owner_type == BankOwnerType.COMPANY,
            BankAccount.status != BankAccountStatus.REPLACED,
        )
        .values(status=BankAccountStatus.REPLACED)
    )
    account = BankAccount(
        company_id=actor.company_id,
        owner_type=BankOwnerType.COMPANY,
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
        action=audit.FUNDING_ACCOUNT_CONNECTED,
        entity_type="bank_account",
        entity_id=account.id,
        before={"account_last4": previous.account_last4} if previous else None,
        after={"account_last4": account.account_last4},
    )
    _company_out(db, company, actor)
    return BankAccountOut.model_validate(account)


@router.put("/company/pay-schedule", response_model=list[PayPeriodOut])
def set_pay_schedule(
    body: PayScheduleIn, actor: Actor = Depends(require_admin), db: Session = Depends(get_db)
):
    company = lock_company(db, actor)
    before = {
        "first_pay_date": company.first_pay_date,
        "cutoff_lead_days": company.cutoff_lead_days,
    }
    set_schedule(db, company, body.first_pay_date, body.cutoff_lead_days, actor)
    audit.record(
        db,
        actor=actor,
        action=audit.PAY_SCHEDULE_SET,
        entity_type="company",
        entity_id=company.id,
        before=before,
        after={
            "schedule": company.pay_schedule,
            "first_pay_date": company.first_pay_date,
            "cutoff_lead_days": company.cutoff_lead_days,
        },
    )
    _company_out(db, company, actor)
    return list_periods(db, actor)


@router.get("/pay-periods", response_model=list[PayPeriodOut])
def list_pay_periods(actor: Actor = Depends(require_staff), db: Session = Depends(get_db)):
    """Upcoming + recent periods, newest pay_date last, with each period's regular run id/state."""
    company = lock_company(db, actor)
    ensure_future_periods(db, company, actor)
    return list_periods(db, actor)


def _set_address(company: Company, address: AddressIn) -> None:
    company.address_line1 = address.line1
    company.address_line2 = address.line2
    company.city = address.city
    company.state = address.state
    company.zip = address.zip


def _profile(company: Company) -> dict:
    return {
        "legal_name": company.legal_name,
        "ein_last4": company.ein_last4,
        "address": {
            "line1": company.address_line1,
            "line2": company.address_line2,
            "city": company.city,
            "state": company.state,
            "zip": company.zip,
        },
    }


def _funding_account(db: Session, actor: Actor) -> BankAccount | None:
    return db.scalar(
        scoped(select(BankAccount), BankAccount, actor)
        .where(
            BankAccount.owner_type == BankOwnerType.COMPANY,
            BankAccount.status == BankAccountStatus.VERIFIED,
        )
        .order_by(BankAccount.created_at.desc(), BankAccount.id)
        .limit(1)
    )


def _company_out(db: Session, company: Company, actor: Actor) -> CompanyOut:
    """Caller holds the company lock; stamp completion once and return masked setup data."""
    account = _funding_account(db, actor)
    # Two retained memberships means someone besides the founding Admin was invited;
    # this remains consistent when viewed by a different staff member.
    members = db.scalars(
        scoped(select(Membership.id), Membership, actor).where(
            Membership.status != MembershipStatus.REMOVED
        )
    ).all()
    profile = bool(
        company.legal_name
        and company.ein_last4
        and company.address_line1
        and company.city
        and company.state == "CA"
        and company.zip
    )
    schedule = company.pay_schedule is not None and company.first_pay_date is not None
    complete = bool(profile and account and schedule and len(members) >= 2)
    if complete and company.setup_completed_at is None:
        company.setup_completed_at = clock.now()
        audit.record(
            db,
            actor=actor,
            action=audit.COMPANY_UPDATED,
            entity_type="company",
            entity_id=company.id,
            after={"setup_completed_at": company.setup_completed_at},
        )
        db.flush()
    return CompanyOut(
        id=company.id,
        legal_name=company.legal_name,
        ein_last4=company.ein_last4,
        address=AddressOut(**_profile(company)["address"]),
        pay_schedule=company.pay_schedule,
        first_pay_date=company.first_pay_date,
        cutoff_lead_days=company.cutoff_lead_days,
        funding_account=BankAccountOut.model_validate(account) if account else None,
        setup=SetupChecklist(
            company_profile=profile,
            funding_account=account is not None,
            pay_schedule=schedule,
            team_invited=len(members) >= 2,
            complete=complete,
        ),
    )


class CompanyValidationError(AppError):
    status_code = 422
    code = "invalid_company_profile"


def _normalize_ein(value: str) -> str:
    digits = value.replace("-", "")
    if len(digits) != 9 or not digits.isascii() or not digits.isdigit():
        raise CompanyValidationError("Enter a nine-digit EIN.", code="invalid_ein")
    return digits
