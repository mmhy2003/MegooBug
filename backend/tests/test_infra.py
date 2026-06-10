"""Sanity check that the test database scaffold works."""
from sqlalchemy import text


async def test_db_connects(db):
    result = await db.execute(text("SELECT 1"))
    assert result.scalar() == 1


async def test_schema_created(db):
    result = await db.execute(text("SELECT count(*) FROM events"))
    assert result.scalar() == 0
