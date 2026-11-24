"""Tenant isolation helpers (NFR-7). Use these instead of `session.get(Model, id)` for anything
company-scoped: `session.get` does NOT check the tenant.

    employee = get_scoped(db, Employee, employee_id, actor)          # 404 if other company
    stmt = scoped(select(Employee), Employee, actor)                  # adds WHERE company_id = ...
"""

import uuid

from sqlalchemy import Select
from sqlalchemy.orm import Session

from app.auth.deps import Actor
from app.errors import NotFound


def scoped(stmt: Select, model: type, actor: Actor) -> Select:
    return stmt.where(model.company_id == actor.company_id)


def get_scoped[T](db: Session, model: type[T], obj_id: uuid.UUID, actor: Actor) -> T:
    obj = db.get(model, obj_id)
    # Same 404 for "doesn't exist" and "belongs to another company": never leak existence.
    if obj is None or obj.company_id != actor.company_id:  # type: ignore[attr-defined]
        raise NotFound(f"{model.__name__} not found.")
    return obj
