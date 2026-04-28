"""initial_schema

Baseline migration representing the current database schema.
All tables were created via create_all before Alembic was set up.

Revision ID: cbed4243c5bc
Revises:
Create Date: 2026-04-28 11:36:27.823142

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = 'cbed4243c5bc'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Baseline — all tables already exist."""
    pass


def downgrade() -> None:
    """Baseline — nothing to undo."""
    pass
