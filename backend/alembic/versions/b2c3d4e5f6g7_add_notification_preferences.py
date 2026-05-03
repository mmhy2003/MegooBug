"""add notification_preferences column to users

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-03 09:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6g7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_PREFS = '{"new_issue":{"inapp":true,"email":true},"regression":{"inapp":true,"email":true},"assigned":{"inapp":true,"email":true}}'


def upgrade() -> None:
    """Add notification_preferences JSONB column with defaults."""
    op.add_column(
        'users',
        sa.Column(
            'notification_preferences',
            JSONB,
            nullable=False,
            server_default=DEFAULT_PREFS,
        ),
    )


def downgrade() -> None:
    """Remove notification_preferences column."""
    op.drop_column('users', 'notification_preferences')
