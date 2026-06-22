"""Add indexes behind the dashboard aggregate read queries.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-22

Uses if_not_exists to stay idempotent alongside the create_all safety net
in app/main.py, which builds the same indexes from model metadata on startup.

Note: CONCURRENT index builds cannot be used here because app/main.py holds
a Postgres advisory lock (pg_advisory_lock 727274) across the entire migration,
and CREATE INDEX CONCURRENTLY requires waiting for all transactions — including
that advisory lock holder — creating a deadlock. Regular CREATE INDEX is used
instead; the advisory lock already serialises concurrent workers.
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'ix_events_received_at', 'events', ['received_at'],
        if_not_exists=True,
    )
    op.create_index(
        'ix_events_project_received_at', 'events', ['project_id', 'received_at'],
        if_not_exists=True,
    )
    op.create_index(
        'ix_issues_project_status', 'issues', ['project_id', 'status'],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index(
        'ix_issues_project_status', table_name='issues',
        if_exists=True,
    )
    op.drop_index(
        'ix_events_project_received_at', table_name='events',
        if_exists=True,
    )
    op.drop_index(
        'ix_events_received_at', table_name='events',
        if_exists=True,
    )
