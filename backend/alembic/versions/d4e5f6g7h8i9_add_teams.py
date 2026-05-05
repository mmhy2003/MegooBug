"""add teams tables and project team_id FK

Revision ID: d4e5f6g7h8i9
Revises: c3d4e5f6g7h8
Create Date: 2026-05-05 11:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6g7h8i9'
down_revision: Union[str, None] = 'c3d4e5f6g7h8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create teams infrastructure.

    1. Create team_number_seq sequence
    2. Create teams table
    3. Create team_members table
    4. Add team_id FK to projects
    5. Create a default team and add all existing users to it
    """
    # 1) Sequence
    op.execute("CREATE SEQUENCE IF NOT EXISTS team_number_seq START 1")

    # 2) Teams table
    op.create_table(
        'teams',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column('team_number', sa.Integer(), nullable=False,
                  server_default=sa.text("nextval('team_number_seq')")),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('slug', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text("now()")),
    )
    op.create_unique_constraint('uq_teams_slug', 'teams', ['slug'])
    op.create_unique_constraint('uq_teams_team_number', 'teams', ['team_number'])
    op.create_index('ix_teams_slug', 'teams', ['slug'])
    op.create_index('ix_teams_team_number', 'teams', ['team_number'])

    # 3) Team members table
    op.create_table(
        'team_members',
        sa.Column('team_id', UUID(as_uuid=True),
                  sa.ForeignKey('teams.id', ondelete='CASCADE'),
                  primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'),
                  primary_key=True),
        sa.Column('role', sa.Enum('admin', 'member', name='teamrole',
                                  create_type=True),
                  nullable=False, server_default='member'),
        sa.Column('joined_at', sa.DateTime(timezone=True),
                  server_default=sa.text("now()")),
    )
    op.create_unique_constraint(
        'uq_team_members_team_user', 'team_members', ['team_id', 'user_id']
    )

    # 4) Add team_id to projects
    op.add_column(
        'projects',
        sa.Column('team_id', UUID(as_uuid=True),
                  sa.ForeignKey('teams.id', ondelete='SET NULL'),
                  nullable=True),
    )
    op.create_index('ix_projects_team_id', 'projects', ['team_id'])

    # 5) Create default team and add all existing users
    op.execute("""
        INSERT INTO teams (id, name, slug, created_at)
        VALUES (gen_random_uuid(), 'Default', 'default', now())
    """)
    op.execute("""
        INSERT INTO team_members (team_id, user_id, role, joined_at)
        SELECT t.id, u.id, 'member', now()
        FROM teams t, users u
        WHERE t.slug = 'default'
    """)
    # Make the first admin user (by created_at) the team admin
    op.execute("""
        UPDATE team_members
        SET role = 'admin'
        WHERE user_id = (
            SELECT id FROM users WHERE role = 'admin'::userrole ORDER BY created_at LIMIT 1
        )
        AND team_id = (SELECT id FROM teams WHERE slug = 'default')
    """)


def downgrade() -> None:
    """Remove teams infrastructure."""
    op.drop_index('ix_projects_team_id', table_name='projects')
    op.drop_column('projects', 'team_id')
    op.drop_table('team_members')
    op.drop_table('teams')
    op.execute("DROP SEQUENCE IF EXISTS team_number_seq")
    op.execute("DROP TYPE IF EXISTS teamrole")
