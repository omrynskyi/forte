"""Every enum in the domain. Stored as VARCHAR + CHECK (native_enum=False), so adding a value is
a small migration. Values are lowercase snake_case and are also the API values."""

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    PAYROLL_MANAGER = "payroll_manager"
    EMPLOYEE = "employee"


class MembershipStatus(StrEnum):
    INVITED = "invited"  # invite sent, never signed in
    ACTIVE = "active"
    FORMER = "former"  # Former Employee: read-only access to own paystubs (TERM-2)
    REMOVED = "removed"  # no access at all (e.g. an Admin/PM removed from the team)


class PaySchedule(StrEnum):
    BIWEEKLY = "biweekly"  # the only schedule in the MVP (D3)


class EmploymentStatus(StrEnum):
    ACTIVE = "active"
    TERMINATED = "terminated"


class SeparationType(StrEnum):
    INVOLUNTARY = "involuntary"  # final pay due on the last day
    VOLUNTARY_WITH_NOTICE = "voluntary_with_notice"  # >= 72h notice: due on the last day
    VOLUNTARY_WITHOUT_NOTICE = "voluntary_without_notice"  # due within 72h of the last day


class PayType(StrEnum):
    SALARY = "salary"  # amount_cents = annual salary
    HOURLY = "hourly"  # amount_cents = cents per hour


class FedFilingStatus(StrEnum):
    SINGLE = "single"  # "Single or married filing separately"
    MARRIED_JOINTLY = "married_jointly"
    HEAD_OF_HOUSEHOLD = "head_of_household"


class CaFilingStatus(StrEnum):
    SINGLE = "single"
    MARRIED = "married"
    HEAD_OF_HOUSEHOLD = "head_of_household"


class BankOwnerType(StrEnum):
    COMPANY = "company"  # funding account
    EMPLOYEE = "employee"  # direct deposit


class AccountType(StrEnum):
    CHECKING = "checking"
    SAVINGS = "savings"


class BankAccountStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"
    REPLACED = "replaced"  # superseded by a newer account; kept for history


class TimesheetStatus(StrEnum):
    OPEN = "open"  # employee can edit
    APPROVED = "approved"  # manager approved; employee can't edit
    REJECTED = "rejected"  # manager rejected with a note; employee edits -> back to OPEN
    LOCKED = "locked"  # the period's regular run was submitted (TIME-3)


class RunType(StrEnum):
    REGULAR = "regular"
    BONUS = "bonus"  # P1 (A-11)
    CORRECTION = "correction"
    FINAL = "final"


class RunState(StrEnum):
    """The 7-state machine (D7). Transitions live in app/payroll/states.py and nowhere else."""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    PROCESSING = "processing"
    PAID = "paid"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CorrectionReason(StrEnum):
    MISSED_HOURS = "missed_hours"  # the only reason in the MVP (D11)


class MagicLinkPurpose(StrEnum):
    LOGIN = "login"
    INVITE = "invite"


class PayoutStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
