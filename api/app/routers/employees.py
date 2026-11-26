"""Employee records and compensation (EMP-1..5, NFR-6). Task B-05.

- EMP-1: POST creates Employee (next employee_number in the company), first Compensation, an
  EMPLOYEE membership (INVITED) and sends an invite magic link.
- EMP-2: compensation is append-only; GET returns history newest first with is_current.
- EMP-3: a member can't add compensation for their own employee record -> 403 "own_compensation".
- Reveal (NFR-6): returns the full SSN or deposit account number and writes
  SENSITIVE_FIELD_REVEALED (masked values only in the audit row).
- Audit EMPLOYEE_CREATED / EMPLOYEE_UPDATED / COMPENSATION_SET.
- Termination is NOT here: see routers/terminations.py (A-08).
"""

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, status
from fastapi.routing import APIRoute
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app import audit, clock
from app.adapters import get_email_sender
from app.adapters.email import EmailSender
from app.auth.deps import Actor, require_staff
from app.auth.scoping import get_scoped, scoped
from app.auth.tokens import issue_magic_link
from app.db import get_db
from app.errors import Conflict, Forbidden, NotFound
from app.models import Company, Compensation, Employee, Membership, User
from app.models.enums import MagicLinkPurpose, MembershipStatus, Role
from app.schemas.common import AddressOut, BankAccountOut
from app.schemas.employees import (
    CompensationIn,
    CompensationOut,
    EmployeeCreate,
    EmployeeListItem,
    EmployeeOut,
    EmployeeUpdate,
    RevealIn,
    RevealOut,
)
from app.schemas.me import WithholdingOut
from app.security.crypto import last4
from app.services.readiness import (
    current_compensation,
    current_deposit_account,
    current_withholding,
    readiness,
)


class EmployeeRoute(APIRoute):
    """Keep employee details, compensation and revealed secrets out of response caches."""

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def no_store(request):
            response = await handler(request)
            response.headers["Cache-Control"] = "no-store"
            return response

        return no_store


router = APIRouter(prefix="/api/employees", tags=["employees"], route_class=EmployeeRoute)


@router.get("", response_model=list[EmployeeListItem])
def list_employees(actor: Actor = Depends(require_staff), db: Session = Depends(get_db)):
    employees = db.scalars(
        scoped(select(Employee), Employee, actor).order_by(
            Employee.last_name, Employee.first_name, Employee.employee_number
        )
    ).all()
    result = []
    for employee in employees:
        member = _membership(db, employee, actor)
        comp = current_compensation(db, employee.id, clock.today_pacific())
        ready = readiness(db, employee, clock.today_pacific())
        result.append(
            EmployeeListItem(
                id=employee.id,
                employee_number=employee.employee_number,
                name=f"{employee.first_name} {employee.last_name}",
                email=employee.email,
                job_title=employee.job_title,
                pay_type=comp.pay_type if comp else None,
                pay_amount_cents=comp.amount_cents if comp else None,
                status=employee.status,
                membership_status=member.status if member else None,
                ready=ready.ready,
                missing=ready.missing,
            )
        )
    return result


@router.post("", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED)
def create_employee(
    body: EmployeeCreate,
    actor: Actor = Depends(require_staff),
    db: Session = Depends(get_db),
    email: EmailSender = Depends(get_email_sender),
):
    # Serialize employee numbering per company. This lock is shared with company setup.
    company = db.scalar(select(Company).where(Company.id == actor.company_id).with_for_update())
    if company is None:
        raise NotFound("Company not found.")
    normalized = str(body.email).lower()
    if (
        db.scalar(
            scoped(select(Employee.id), Employee, actor).where(
                func.lower(Employee.email) == normalized
            )
        )
        is not None
    ):
        raise Conflict("This email cannot be used for a new employee.", code="email_in_use")
    # Reuse users who signed up but have no company, without changing existing memberships.
    db.execute(
        insert(User).values(email=normalized).on_conflict_do_nothing(index_elements=[User.email])
    )
    user = db.scalar(select(User).where(User.email == normalized).with_for_update())
    # Authentication bootstrap: membership is discovered by the selected user, not request tenant ids.
    # Use the same generic error for own-company and other-company memberships.
    if db.scalar(select(Membership.id).where(Membership.user_id == user.id)) is not None:
        raise Conflict("This email cannot be used for a new employee.", code="email_in_use")
    number = db.scalar(scoped(select(func.max(Employee.employee_number)), Employee, actor)) or 0
    employee = Employee(
        company_id=actor.company_id,
        employee_number=number + 1,
        first_name=body.first_name,
        last_name=body.last_name,
        email=normalized,
        job_title=body.job_title,
        hire_date=body.hire_date,
    )
    db.add(employee)
    db.flush()
    member = Membership(
        company_id=actor.company_id,
        user_id=user.id,
        employee_id=employee.id,
        role=Role.EMPLOYEE,
        status=MembershipStatus.INVITED,
        invited_by_membership_id=actor.membership_id,
    )
    db.add(member)
    db.flush()
    audit.record(
        db,
        actor=actor,
        action=audit.EMPLOYEE_CREATED,
        entity_type="employee",
        entity_id=employee.id,
        after=_employee_snapshot(employee),
    )
    _append_compensation(db, employee, body.compensation, actor)
    audit.record(
        db,
        actor=actor,
        action=audit.MEMBER_INVITED,
        entity_type="membership",
        entity_id=member.id,
        after={"email": normalized, "role": member.role},
    )
    issue_magic_link(db, user, MagicLinkPurpose.INVITE, email)
    return _employee_out(db, employee, actor)


@router.get("/{employee_id}", response_model=EmployeeOut)
def get_employee(
    employee_id: uuid.UUID, actor: Actor = Depends(require_staff), db: Session = Depends(get_db)
):
    return _employee_out(db, get_scoped(db, Employee, employee_id, actor), actor)


@router.patch("/{employee_id}", response_model=EmployeeOut)
def update_employee(
    employee_id: uuid.UUID,
    body: EmployeeUpdate,
    actor: Actor = Depends(require_staff),
    db: Session = Depends(get_db),
):
    employee = get_scoped(db, Employee, employee_id, actor)
    db.refresh(employee, with_for_update=True)
    if (
        employee.id == actor.employee_id
        and body.job_title is not None
        and body.job_title != employee.job_title
    ):
        raise Forbidden("Someone else must change your job title.", code="own_job_title")
    before = _employee_snapshot(employee)
    for field in ("first_name", "last_name", "job_title"):
        value = getattr(body, field)
        if value is not None:
            setattr(employee, field, value)
    audit.record(
        db,
        actor=actor,
        action=audit.EMPLOYEE_UPDATED,
        entity_type="employee",
        entity_id=employee.id,
        before=before,
        after=_employee_snapshot(employee),
    )
    db.flush()
    return _employee_out(db, employee, actor)


@router.get("/{employee_id}/compensations", response_model=list[CompensationOut])
def list_compensations(
    employee_id: uuid.UUID, actor: Actor = Depends(require_staff), db: Session = Depends(get_db)
):
    employee = get_scoped(db, Employee, employee_id, actor)
    current = current_compensation(db, employee.id, clock.today_pacific())
    versions = db.scalars(
        scoped(select(Compensation), Compensation, actor)
        .where(Compensation.employee_id == employee.id)
        .order_by(Compensation.effective_date.desc(), Compensation.created_at.desc())
    ).all()
    return [_compensation_out(db, version, current, actor) for version in versions]


@router.post(
    "/{employee_id}/compensations",
    response_model=CompensationOut,
    status_code=status.HTTP_201_CREATED,
)
def add_compensation(
    employee_id: uuid.UUID,
    body: CompensationIn,
    actor: Actor = Depends(require_staff),
    db: Session = Depends(get_db),
):
    employee = get_scoped(db, Employee, employee_id, actor)
    if employee.id == actor.employee_id:
        raise Forbidden("Someone else must set your compensation.", code="own_compensation")
    db.refresh(employee, with_for_update=True)
    compensation = _append_compensation(db, employee, body, actor)
    current = current_compensation(db, employee.id, clock.today_pacific())
    return _compensation_out(db, compensation, current, actor)


@router.post("/{employee_id}/reveal", response_model=RevealOut)
def reveal_sensitive(
    employee_id: uuid.UUID,
    body: RevealIn,
    actor: Actor = Depends(require_staff),
    db: Session = Depends(get_db),
):
    employee = get_scoped(db, Employee, employee_id, actor)
    if body.field == "ssn":
        value = employee.ssn
    else:
        account = current_deposit_account(db, employee.id)
        value = account.account_number if account else None
    if not value:
        raise NotFound("This employee has not provided that information yet.")
    audit.record(
        db,
        actor=actor,
        action=audit.SENSITIVE_FIELD_REVEALED,
        entity_type="employee",
        entity_id=employee.id,
        after={"field": body.field, "last4": last4(value)},
    )
    db.flush()
    return RevealOut(field=body.field, value=value)


def _membership(db: Session, employee: Employee, actor: Actor) -> Membership | None:
    return db.scalar(
        scoped(select(Membership), Membership, actor).where(Membership.employee_id == employee.id)
    )


def _member_name(db: Session, member_id: uuid.UUID | None, actor: Actor) -> str | None:
    if member_id is None:
        return None
    member = get_scoped(db, Membership, member_id, actor)
    if member.employee_id:
        employee = get_scoped(db, Employee, member.employee_id, actor)
        return f"{employee.first_name} {employee.last_name}"
    return db.get(User, member.user_id).email


def _compensation_out(
    db: Session, comp: Compensation, current: Compensation | None, actor: Actor
) -> CompensationOut:
    return CompensationOut(
        id=comp.id,
        pay_type=comp.pay_type,
        amount_cents=comp.amount_cents,
        effective_date=comp.effective_date,
        created_at=comp.created_at,
        set_by_name=_member_name(db, comp.created_by_membership_id, actor),
        is_current=current is not None and current.id == comp.id,
    )


def _append_compensation(
    db: Session, employee: Employee, body: CompensationIn, actor: Actor
) -> Compensation:
    previous = current_compensation(db, employee.id, clock.today_pacific())
    same_date = db.scalar(
        scoped(select(Compensation), Compensation, actor)
        .where(
            Compensation.employee_id == employee.id,
            Compensation.effective_date == body.effective_date,
        )
        .order_by(Compensation.created_at.desc())
        .limit(1)
    )
    created_at = clock.now()
    # Keep effective-date ties deterministic even when two edits share one clock tick.
    if same_date and same_date.created_at >= created_at:
        created_at = same_date.created_at + timedelta(microseconds=1)
    comp = Compensation(
        company_id=actor.company_id,
        employee_id=employee.id,
        created_by_membership_id=actor.membership_id,
        created_at=created_at,
        **body.model_dump(),
    )
    db.add(comp)
    db.flush()
    audit.record(
        db,
        actor=actor,
        action=audit.COMPENSATION_SET,
        entity_type="employee",
        entity_id=employee.id,
        before={
            "amount_cents": previous.amount_cents,
            "pay_type": previous.pay_type,
            "effective_date": previous.effective_date,
        }
        if previous
        else None,
        after={
            "amount_cents": comp.amount_cents,
            "pay_type": comp.pay_type,
            "effective_date": comp.effective_date,
        },
    )
    return comp


def _employee_snapshot(employee: Employee) -> dict:
    return {
        "first_name": employee.first_name,
        "last_name": employee.last_name,
        "email": employee.email,
        "employee_number": employee.employee_number,
        "job_title": employee.job_title,
        "hire_date": employee.hire_date,
    }


def _employee_out(db: Session, employee: Employee, actor: Actor) -> EmployeeOut:
    member = _membership(db, employee, actor)
    comp = current_compensation(db, employee.id, clock.today_pacific())
    withholding = current_withholding(db, employee.id, clock.today_pacific())
    account = current_deposit_account(db, employee.id)
    ready = readiness(db, employee, clock.today_pacific())
    address = None
    if employee.address_line1 and employee.city and employee.state and employee.zip:
        address = AddressOut(
            line1=employee.address_line1,
            line2=employee.address_line2,
            city=employee.city,
            state=employee.state,
            zip=employee.zip,
        )
    return EmployeeOut(
        id=employee.id,
        employee_number=employee.employee_number,
        first_name=employee.first_name,
        last_name=employee.last_name,
        email=employee.email,
        job_title=employee.job_title,
        hire_date=employee.hire_date,
        dob=employee.dob,
        ssn_last4=employee.ssn_last4,
        address=address,
        status=employee.status,
        end_date=employee.end_date,
        separation_type=employee.separation_type,
        membership_status=member.status if member else None,
        role=member.role if member else None,
        compensation=_compensation_out(db, comp, comp, actor) if comp else None,
        withholding=WithholdingOut.model_validate(withholding) if withholding else None,
        deposit_account=BankAccountOut.model_validate(account) if account else None,
        ready=ready.ready,
        missing=ready.missing,
    )
