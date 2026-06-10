"""Add indexes for retention cleanup predicates.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6g7h8i9
Create Date: 2026-06-10

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6g7h8i9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index('ix_events_timestamp', 'events', ['timestamp'])
    op.create_index('ix_issues_last_seen', 'issues', ['last_seen'])


def downgrade() -> None:
    op.drop_index('ix_issues_last_seen', table_name='issues')
    op.drop_index('ix_events_timestamp', table_name='events')
