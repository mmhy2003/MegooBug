"""Add indexes behind the dashboard aggregate read queries.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-22

Each CREATE/DROP runs in its OWN autocommit transaction (autocommit_block),
NOT in Alembic's default single migration transaction. Two reasons:

1. Multi-table deadlock with concurrent ingest. The celery-ingest worker runs
   process_event continuously: within one transaction it writes `issues`
   (RowExclusive) then `events` (RowExclusive). If this migration created all
   three indexes in one transaction, it would hold a SHARE lock on `events`
   (from the first two indexes) while requesting SHARE on `issues` (the third)
   — while an ingest txn holds RowExclusive on `issues` and wants RowExclusive
   on `events`. That is a lock cycle → `DeadlockDetectedError`, which aborts
   app startup (migrations run in the startup lifespan). Autocommit makes each
   index its own transaction, so the migration holds at most ONE table's lock
   at a time and never forms a cycle — it briefly waits for an in-flight ingest
   txn, then proceeds.

2. CONCURRENT builds are still not an option here: app/main.py runs Alembic
   during startup while holding pg_advisory_lock(727274) on a connection with
   an open transaction, and CREATE INDEX CONCURRENTLY waits for all concurrent
   transactions (including that lock holder) — which never ends. So we use
   plain CREATE INDEX (brief SHARE lock that pauses ingest writes for the build
   only; reads are unaffected, and ingest writes are Celery-queued so they
   simply wait). For a very large table, an operator may pre-create these
   indexes manually with CONCURRENTLY before deploying so the migration no-ops.

if_not_exists / if_exists keep this idempotent alongside the create_all safety
net in app/main.py, which builds the same indexes from model metadata.
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # autocommit_block => each statement commits on its own; the migration
    # never holds locks on two tables at once (see module docstring).
    with op.get_context().autocommit_block():
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
    with op.get_context().autocommit_block():
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
