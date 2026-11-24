"""Audit log (AUD-1, AUD-2). Task B-08.

- Admin: everything in the company. Payroll Manager: only entries where they are the actor.
- Filters: entity_type, entity_id, action, limit (default 100, max 500). Newest first.
- `summary` comes from app/services/audit_text.py::summarize(entry, names) which this task creates:
  one plain sentence per action constant in app/audit.py.
- There is no update or delete endpoint, and the DB trigger rejects both anyway (AUD-2).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.deps import Actor, require_staff
from app.db import get_db
from app.errors import todo
from app.schemas.audit import AuditEntryOut

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=list[AuditEntryOut])
def list_audit(
    entity_type: str | None = None,
    entity_id: str | None = None,
    action: str | None = None,
    limit: int = 100,
    actor: Actor = Depends(require_staff),
    db: Session = Depends(get_db),
):
    todo("B-08")
