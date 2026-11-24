import uuid

from pydantic import EmailStr

from app.models.enums import MembershipStatus, Role
from app.schemas.common import ApiModel


class MagicLinkRequest(ApiModel):
    email: EmailStr


class MagicLinkAccepted(ApiModel):
    message: str = "If that email can sign in, we sent a link. It works once, for 15 minutes."


class VerifyRequest(ApiModel):
    token: str


class DevLoginRequest(ApiModel):
    email: EmailStr


class CompanyBrief(ApiModel):
    id: uuid.UUID
    legal_name: str
    setup_complete: bool


class MembershipBrief(ApiModel):
    id: uuid.UUID
    role: Role
    status: MembershipStatus


class OnboardingStatus(ApiModel):
    personal_info: bool
    withholding: bool
    bank_account: bool
    complete: bool


class MeOut(ApiModel):
    """Everything the frontend needs to route a signed-in user:
    - no membership                 -> /setup (create a company)
    - role admin/payroll_manager    -> staff app (/admin or /payroll)
    - employee, onboarding not done -> /me/onboarding
    - status former                 -> /me/former
    """

    user_id: uuid.UUID
    email: str
    display_name: str | None
    membership: MembershipBrief | None
    company: CompanyBrief | None
    employee_id: uuid.UUID | None
    onboarding: OnboardingStatus | None  # set when on payroll


class DevUserOut(ApiModel):
    email: str
    display_name: str
    role: Role
    status: MembershipStatus
