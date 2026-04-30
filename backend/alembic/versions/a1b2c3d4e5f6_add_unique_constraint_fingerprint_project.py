"""add unique constraint on issues(fingerprint, project_id)

Deduplicates existing rows (keeps oldest per group, merges event counts),
then adds a UNIQUE constraint to prevent future duplicates.

Revision ID: a1b2c3d4e5f6
Revises: cbed4243c5bc
Create Date: 2026-04-30 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'cbed4243c5bc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Deduplicate issues and add unique constraint."""
    conn = op.get_bind()

    # Step 1: Find duplicate groups (same fingerprint + project_id with multiple rows)
    dupes = conn.execute(sa.text("""
        SELECT fingerprint, project_id, MIN(first_seen) AS keep_first_seen
        FROM issues
        GROUP BY fingerprint, project_id
        HAVING COUNT(*) > 1
    """)).fetchall()

    for fingerprint, project_id, keep_first_seen in dupes:
        # Find the canonical issue (oldest by first_seen)
        keeper = conn.execute(sa.text("""
            SELECT id, event_count FROM issues
            WHERE fingerprint = :fp AND project_id = :pid
            ORDER BY first_seen ASC
            LIMIT 1
        """), {"fp": fingerprint, "pid": project_id}).fetchone()

        if not keeper:
            continue

        keeper_id = keeper[0]

        # Find duplicate issue IDs (all except the keeper)
        dup_rows = conn.execute(sa.text("""
            SELECT id, event_count FROM issues
            WHERE fingerprint = :fp AND project_id = :pid AND id != :keeper_id
        """), {"fp": fingerprint, "pid": project_id, "keeper_id": keeper_id}).fetchall()

        total_extra_events = sum(row[1] for row in dup_rows)
        dup_ids = [row[0] for row in dup_rows]

        # Reassign events from duplicates to the keeper
        for dup_id in dup_ids:
            conn.execute(sa.text("""
                UPDATE events SET issue_id = :keeper_id WHERE issue_id = :dup_id
            """), {"keeper_id": keeper_id, "dup_id": dup_id})

        # Update keeper's event_count and last_seen
        conn.execute(sa.text("""
            UPDATE issues SET
                event_count = event_count + :extra,
                last_seen = (SELECT MAX(last_seen) FROM issues WHERE fingerprint = :fp AND project_id = :pid)
            WHERE id = :keeper_id
        """), {"extra": total_extra_events, "fp": fingerprint, "pid": project_id, "keeper_id": keeper_id})

        # Reassign notifications from duplicates to keeper
        for dup_id in dup_ids:
            conn.execute(sa.text("""
                UPDATE notifications SET issue_id = :keeper_id WHERE issue_id = :dup_id
            """), {"keeper_id": keeper_id, "dup_id": dup_id})

        # Delete duplicate issues
        for dup_id in dup_ids:
            conn.execute(sa.text("""
                DELETE FROM issues WHERE id = :dup_id
            """), {"dup_id": dup_id})

    # Step 2: Drop the old non-unique index if it exists
    op.execute(sa.text("DROP INDEX IF EXISTS ix_issues_fingerprint_project"))

    # Step 3: Add unique constraint
    op.create_unique_constraint(
        "uq_issues_fingerprint_project",
        "issues",
        ["fingerprint", "project_id"],
    )


def downgrade() -> None:
    """Remove unique constraint, restore non-unique index."""
    op.drop_constraint("uq_issues_fingerprint_project", "issues", type_="unique")
    op.create_index(
        "ix_issues_fingerprint_project",
        "issues",
        ["fingerprint", "project_id"],
    )
