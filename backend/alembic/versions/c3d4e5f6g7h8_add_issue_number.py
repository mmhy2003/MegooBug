"""add issue_number column and sequence for Sentry-compatible short IDs

Revision ID: c3d4e5f6g7h8
Revises: b2c3d4e5f6g7
Create Date: 2026-05-05 11:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6g7h8'
down_revision: Union[str, None] = 'b2c3d4e5f6g7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add issue_number_seq and issue_number column.

    1. Create the sequence
    2. Add the column with the sequence as default
    3. Backfill existing rows with sequential numbers
    4. Create unique index
    """
    # Create the sequence
    op.execute("CREATE SEQUENCE IF NOT EXISTS issue_number_seq START 1")

    # Add column
    op.add_column(
        'issues',
        sa.Column(
            'issue_number',
            sa.Integer(),
            nullable=True,
            server_default=sa.text("nextval('issue_number_seq')"),
        ),
    )

    # Backfill existing issues (ordered by first_seen for deterministic numbering)
    op.execute("""
        WITH numbered AS (
            SELECT id, ROW_NUMBER() OVER (ORDER BY first_seen) AS rn
            FROM issues
            WHERE issue_number IS NULL
        )
        UPDATE issues
        SET issue_number = numbered.rn
        FROM numbered
        WHERE issues.id = numbered.id
    """)

    # Advance the sequence past all backfilled values
    op.execute("""
        SELECT setval('issue_number_seq',
            COALESCE((SELECT MAX(issue_number) FROM issues), 0) + 1,
            false
        )
    """)

    # Create unique index
    op.create_unique_constraint('uq_issues_issue_number', 'issues', ['issue_number'])
    op.create_index('ix_issues_issue_number', 'issues', ['issue_number'])


def downgrade() -> None:
    """Remove issue_number column and sequence."""
    op.drop_index('ix_issues_issue_number', table_name='issues')
    op.drop_constraint('uq_issues_issue_number', 'issues')
    op.drop_column('issues', 'issue_number')
    op.execute("DROP SEQUENCE IF EXISTS issue_number_seq")
