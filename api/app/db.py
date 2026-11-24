"""Database engine and session. Sync SQLAlchemy 2.0 on purpose: simpler for everyone, fast enough.

Rules (see CLAUDE.md):
- One request = one Session = one transaction. `get_db` commits on success, rolls back on error.
- Services never call `session.commit()` themselves. Only `get_db` (requests) and CLI entry
  points (seed) commit. This is what makes "audit entry in the same transaction" (NFR-10) true.
- Run state changes lock the run row with `SELECT ... FOR UPDATE` (NFR-4); see payroll/state_machine.py.
"""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
