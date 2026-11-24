"""Shared test setup. Every test gets a database transaction that is rolled back afterwards, so tests
are isolated and fast. Postgres is required (row locks, JSONB, triggers); storage and email are
in-memory, so CI never needs MinIO or Mailpit.

    def test_something(client, db, as_actor):
        company = f.make_company(db)
        admin = f.make_member(db, company, Role.ADMIN)
        as_actor(admin)                      # every request is now made by this member
        r = client.get("/api/company")

Factories live in tests/factories.py (import as `from tests import factories as f`).
"""

import os

TEST_DB = os.environ.get(
    "FORTE_TEST_DATABASE_URL", "postgresql+psycopg://forte:forte@localhost:5432/forte_test"
)
os.environ["FORTE_DATABASE_URL"] = TEST_DB
os.environ["FORTE_ENV"] = "test"
os.environ["FORTE_STORAGE_BACKEND"] = "memory"
os.environ["FORTE_EMAIL_SENDER"] = "console"
os.environ["FORTE_MOCK_PAYOUT_DELAY_SECONDS"] = "0"

from collections.abc import Callable, Iterator  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.adapters import get_email_sender, get_storage  # noqa: E402
from app.adapters.email import ConsoleEmailSender  # noqa: E402
from app.adapters.storage import MemoryStorage  # noqa: E402
from app.auth.deps import Actor, get_actor  # noqa: E402
from app.db import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Membership  # noqa: E402
from tests import factories as f  # noqa: E402

API_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def engine():
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "alembic"))
    command.upgrade(cfg, "head")  # tests always run against the real migrations
    eng = create_engine(TEST_DB)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine) -> Iterator[Session]:
    conn = engine.connect()
    outer = conn.begin()
    session = Session(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        conn.close()


@pytest.fixture
def storage() -> MemoryStorage:
    return MemoryStorage()


@pytest.fixture
def outbox() -> ConsoleEmailSender:
    return ConsoleEmailSender()


@pytest.fixture
def client(db: Session, storage: MemoryStorage, outbox: ConsoleEmailSender) -> Iterator[TestClient]:
    def _db() -> Iterator[Session]:
        yield db
        db.flush()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_email_sender] = lambda: outbox
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def as_actor(db: Session) -> Callable[[Membership | Actor | None], Actor | None]:
    """Make every following request act as this member (or pass None to sign out)."""

    def _set(who: Membership | Actor | None) -> Actor | None:
        if who is None:
            app.dependency_overrides.pop(get_actor, None)
            return None
        actor = who if isinstance(who, Actor) else f.actor_for(db, who)
        app.dependency_overrides[get_actor] = lambda: actor
        return actor

    return _set
