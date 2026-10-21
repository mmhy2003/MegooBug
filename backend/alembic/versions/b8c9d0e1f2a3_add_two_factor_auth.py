"""add two-factor authentication (TOTP + WebAuthn passkeys)

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-10-21 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_USER_COLUMNS = [
    sa.Column('mfa_required', sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column('totp_secret', sa.Text(), nullable=True),
    sa.Column('totp_pending_secret', sa.Text(), nullable=True),
    sa.Column('totp_enabled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('totp_last_step', sa.BigInteger(), nullable=True),
    sa.Column('webauthn_challenge', sa.Text(), nullable=True),
    sa.Column('webauthn_challenge_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('mfa_pending_jti', sa.String(64), nullable=True),
    sa.Column('mfa_pending_failures', sa.Integer(), nullable=False, server_default='0'),
    sa.Column('mfa_failed_streak', sa.Integer(), nullable=False, server_default='0'),
    sa.Column('mfa_retry_after', sa.DateTime(timezone=True), nullable=True),
]


def upgrade() -> None:
    """Add 2FA columns on users and the webauthn_credentials table."""
    for column in _USER_COLUMNS:
        op.add_column('users', column)

    op.create_table(
        'webauthn_credentials',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'user_id', UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False,
        ),
        sa.Column('credential_id', sa.String(512), nullable=False, unique=True),
        sa.Column('public_key', sa.LargeBinary(), nullable=False),
        sa.Column('sign_count', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('transports', JSONB, nullable=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        'ix_webauthn_credentials_user_id', 'webauthn_credentials', ['user_id']
    )


def downgrade() -> None:
    """Remove 2FA table and columns."""
    op.drop_index('ix_webauthn_credentials_user_id', table_name='webauthn_credentials')
    op.drop_table('webauthn_credentials')
    for column in reversed(_USER_COLUMNS):
        op.drop_column('users', column.name)
