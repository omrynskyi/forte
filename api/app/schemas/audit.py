from datetime import datetime
from typing import Any

from app.schemas.common import ApiModel


class AuditEntryOut(ApiModel):
    id: int
    created_at: datetime
    actor_name: str | None  # None = system
    actor_role: str | None
    action: str
    entity_type: str
    entity_id: str
    summary: str  # plain sentence, e.g. "Ana Lindqvist submitted payroll for Dec 11." (B-08)
    before: dict[str, Any] | None
    after: dict[str, Any] | None
