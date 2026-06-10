"""Shared test fixtures: dedicated Postgres test database + rollback sessions.

Tests run inside the backend container (see `make test-be`), where the
dev-stack Postgres is reachable at host `postgres`. The test database
`megoobug_test` is created from scratch at session start and dropped at
session end — it never touches the dev `megoobug` database.
"""
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import settings
from app.database import Base
import app.models  # noqa: F401 — register all models on Base.metadata

TEST_DB_NAME = "megoobug_test"
# Reuse the app's DSN (user/password/host), swap only the database name.
ADMIN_URL = settings.DATABASE_URL
TEST_URL = ADMIN_URL.rsplit("/", 1)[0] + f"/{TEST_DB_NAME}"


async def _run_admin_sql(*statements: str) -> None:
    """Run statements outside a transaction (needed for CREATE/DROP DATABASE)."""
    admin = create_async_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as conn:
            for stmt in statements:
                await conn.execute(text(stmt))
    finally:
        await admin.dispose()


@pytest.fixture(scope="session")
async def db_engine():
    await _run_admin_sql(
        f"DROP DATABASE IF EXISTS {TEST_DB_NAME} WITH (FORCE)",
        f"CREATE DATABASE {TEST_DB_NAME}",
    )
    engine = create_async_engine(TEST_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()
    await _run_admin_sql(f"DROP DATABASE IF EXISTS {TEST_DB_NAME} WITH (FORCE)")


@pytest.fixture
async def db(db_engine):
    """A session inside a transaction that is rolled back after each test."""
    async with db_engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()
