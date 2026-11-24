"""Test data builders. Add new helpers at the bottom of this file in your PR; don't change the
signatures of existing ones (other tasks rely on them). All data is fake (NFR-9)."""

import itertools
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from app.auth.deps import Actor
from app.models import (
    BankAccount,
    Company,
    Compensation,
    Employee,
    Membership,
    PayPeriod,
    User,
    Withholding,
)
from app.models.enums import (
    AccountType,
    BankAccountStatus,
    BankOwnerType,
    CaFilingStatus,
    FedFilingStatus,
    MembershipStatus,
    PaySchedule,
    PayType,
    Role,
)
from app.security.crypto import last4

_seq = itertools.count(1)


def make_company(db: Session, legal_name: str = "Larkspur Bakery, Inc.") -> Company:
    company = Company(
        legal_name=legal_name,
        ein="12-3456789",
        ein_last4="6789",
        address_line1="1180 Alder Street",
        city="San Jose",
        state="CA",
        zip="95112",
        pay_schedule=PaySchedule.BIWEEKLY,
        first_pay_date=date(2026, 12, 11),
        cutoff_lead_days=2,
    )
    db.add(company)
    db.flush()
    return company


def make_user(db: Session, email: str | None = None) -> User:
    user = User(email=email or f"user{next(_seq)}@larkspur.example")
    db.add(user)
    db.flush()
    return user


def make_employee(
    db: Session,
    company: Company,
    first_name: str = "Devon",
    last_name: str = "Park",
    *,
    pay_type: PayType = PayType.HOURLY,
    amount_cents: int = 2450,  # $24.50/h; for salary pass the ANNUAL amount in cents
    onboarded: bool = True,
    hire_date: date = date(2026, 3, 2),
    email: str | None = None,
) -> Employee:
    n = next(_seq)
    emp = Employee(
        company_id=company.id,
        employee_number=n,
        first_name=first_name,
        last_name=last_name,
        email=email or f"{first_name.lower()}{n}@larkspur.example",
        job_title="Counter lead",
        hire_date=hire_date,
    )
    db.add(emp)
    db.flush()
    db.add(
        Compensation(
            company_id=company.id,
            employee_id=emp.id,
            pay_type=pay_type,
            amount_cents=amount_cents,
            effective_date=hire_date,
        )
    )
    if onboarded:
        emp.dob = date(1995, 6, 1)
        emp.ssn = "123-45-4821"
        emp.ssn_last4 = "4821"
        emp.address_line1 = "411 Willow Glen Way"
        emp.city = "San Jose"
        emp.state = "CA"
        emp.zip = "95125"
        db.add(
            Withholding(
                company_id=company.id,
                employee_id=emp.id,
                effective_date=hire_date,
                fed_filing_status=FedFilingStatus.SINGLE,
                ca_filing_status=CaFilingStatus.SINGLE,
            )
        )
        make_bank_account(db, company, employee=emp)
    db.flush()
    return emp


def make_bank_account(
    db: Session,
    company: Company,
    *,
    employee: Employee | None = None,
    account_number: str = "000123453347",
    status: BankAccountStatus = BankAccountStatus.VERIFIED,
) -> BankAccount:
    acct = BankAccount(
        company_id=company.id,
        owner_type=BankOwnerType.EMPLOYEE if employee else BankOwnerType.COMPANY,
        employee_id=employee.id if employee else None,
        routing_number="110000000",
        account_number=account_number,
        account_last4=last4(account_number),
        account_type=AccountType.CHECKING,
        status=status,
        verified_at=datetime.now(UTC) if status == BankAccountStatus.VERIFIED else None,
    )
    db.add(acct)
    db.flush()
    return acct


def make_member(
    db: Session,
    company: Company,
    role: Role = Role.ADMIN,
    *,
    email: str | None = None,
    employee: Employee | None = None,
    status: MembershipStatus = MembershipStatus.ACTIVE,
) -> Membership:
    user = make_user(db, email or (employee.email if employee else None))
    m = Membership(
        company_id=company.id,
        user_id=user.id,
        role=role,
        status=status,
        employee_id=employee.id if employee else None,
    )
    db.add(m)
    db.flush()
    return m


def actor_for(db: Session, membership: Membership, ip: str | None = "127.0.0.1") -> Actor:
    user = db.get(User, membership.user_id)
    assert user is not None
    return Actor(
        user_id=user.id,
        email=user.email,
        membership_id=membership.id,
        company_id=membership.company_id,
        role=membership.role,
        status=membership.status,
        employee_id=membership.employee_id,
        ip=ip,
    )


def make_pay_period(
    db: Session,
    company: Company,
    pay_date: date = date(2026, 12, 11),
    *,
    cutoff_at: datetime | None = None,
) -> PayPeriod:
    end = pay_date - timedelta(days=5)
    period = PayPeriod(
        company_id=company.id,
        start_date=end - timedelta(days=13),
        end_date=end,
        pay_date=pay_date,
        cutoff_at=cutoff_at or datetime.now(UTC) + timedelta(hours=3),
    )
    db.add(period)
    db.flush()
    return period


def other_company_setup(db: Session) -> tuple[Company, Membership]:
    """A second tenant with its own Admin, for cross-tenant tests (NFR-7)."""
    other = make_company(db, legal_name=f"Other Co {uuid.uuid4().hex[:6]}")
    return other, make_member(db, other, Role.ADMIN)
