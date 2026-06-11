"""Test fixtures. Tests run against a real Postgres database (no DB mocks).

The test database URL can be overridden with ``CENTINELA_TEST_DATABASE_URL``;
it defaults to a local ``centinela_test`` database. We point the app's
``CENTINELA_DATABASE_URL`` at it *before* importing any app module so the
engine and settings bind to the test database.
"""

from __future__ import annotations

import os

TEST_DATABASE_URL = os.environ.get(
    "CENTINELA_TEST_DATABASE_URL",
    "postgresql+psycopg://centinela:centinela@localhost:5432/centinela_test",
)
# Must be set before app modules import their settings/engine.
os.environ["CENTINELA_DATABASE_URL"] = TEST_DATABASE_URL

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ApiKey, Org  # noqa: E402
from app.security import generate_key  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _migrate():
    """Bring the test database schema up to head once per session."""
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    yield


@pytest.fixture()
def db_clean():
    """Truncate all data before each test for isolation."""
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE events, api_keys, orgs CASCADE"))
    yield


@pytest.fixture()
def client(db_clean):
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def make_org_key():
    """Factory: create an org and an API key, returning (org_id, full_key)."""
    def _make(org_name: str = "test-org", key_name: str = "test-key"):
        with SessionLocal() as db:
            org = Org(name=org_name)
            db.add(org)
            db.flush()
            generated = generate_key()
            db.add(
                ApiKey(
                    org_id=org.id,
                    name=key_name,
                    key_prefix=generated.prefix,
                    key_hash=generated.key_hash,
                    salt=generated.salt,
                )
            )
            db.commit()
            return str(org.id), generated.full_key

    return _make
