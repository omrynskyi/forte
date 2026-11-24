import uuid
from datetime import datetime
from typing import Literal

from pydantic import EmailStr

from app.models.enums import MembershipStatus, Role
from app.schemas.common import ApiModel


class MemberOut(ApiModel):
    id: uuid.UUID
    email: str
    display_name: str | None
    role: Role
    status: MembershipStatus
    employee_id: uuid.UUID | None
    created_at: datetime


class InviteIn(ApiModel):
    """Invite an Admin or Payroll Manager. Employees are invited via POST /api/employees (EMP-1)."""

    email: EmailStr
    role: Literal["admin", "payroll_manager"]


class RoleChangeIn(ApiModel):
    role: Literal["admin", "payroll_manager", "employee"]
