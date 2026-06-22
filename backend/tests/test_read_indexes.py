"""The dashboard read indexes are present in the schema built from the models."""
from sqlalchemy import text

EXPECTED = {
    "ix_events_received_at",
    "ix_events_project_received_at",
    "ix_issues_project_status",
}


async def test_dashboard_read_indexes_exist(db):
    rows = (await db.execute(text(
        "SELECT indexname FROM pg_indexes "
        "WHERE tablename IN ('events', 'issues')"
    ))).scalars().all()
    missing = EXPECTED - set(rows)
    assert not missing, f"missing indexes: {missing}"
