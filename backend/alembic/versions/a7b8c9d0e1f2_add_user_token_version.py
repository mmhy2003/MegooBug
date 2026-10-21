"""add token_version column to users

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-10-21 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add token_version (bumped on password change to invalidate JWTs)."""
    op.add_column(
        'users',
        sa.Column(
            'token_version',
            sa.Integer(),
            nullable=False,
            server_default='0',
        ),
    )


def downgrade() -> None:
    """Remove token_version column."""
    op.drop_column('users', 'token_version')
