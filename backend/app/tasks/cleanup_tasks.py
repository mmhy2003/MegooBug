"""Retention cleanup: delete ingested data older than RETENTION_DAYS.

The async core (`_cleanup`) touches Postgres only and is unit-tested.
The Celery task wrapper and the Meilisearch mirror live in this module too
(added alongside) but stay out of the core so tests need neither Celery nor
Meilisearch.
"""
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event
from app.models.issue import Issue
from app.logging import get_logger

logger = get_logger("tasks.cleanup")


async def _cleanup(db: AsyncSession, cutoff: datetime, batch_size: int = 5000) -> dict:
    """Delete stale issues (cascades to their events) and old events.

    Postgres is the source of truth and is cleaned first; each batch commits
    independently so an interrupted run loses nothing.
    Returns ids so the caller can mirror deletions to Meilisearch.
    """
    # Single DELETE ... RETURNING so the predicate is re-evaluated at delete
    # time — an issue revived by concurrent ingestion between plan and execute
    # is skipped, and the returned ids exactly match what was deleted.
    # NOTE: unbatched — the first run on a long backlog cascades all expired
    # issues' events in one transaction; acceptable for a nightly job.
    stale_result = await db.execute(
        delete(Issue).where(Issue.last_seen < cutoff).returning(Issue.id)
    )
    stale_issue_ids = list(stale_result.scalars().all())
    await db.commit()
    if stale_issue_ids:
        logger.info("Retention: deleted %d stale issues", len(stale_issue_ids))

    deleted_event_ids = []
    while True:
        result = await db.execute(
            delete(Event)
            .where(
                Event.id.in_(
                    select(Event.id).where(Event.timestamp < cutoff).limit(batch_size)
                )
            )
            .returning(Event.id)
        )
        batch = list(result.scalars().all())
        await db.commit()
        if not batch:
            break
        deleted_event_ids.extend(batch)
        if len(batch) < batch_size:
            break

    if deleted_event_ids:
        logger.info("Retention: deleted %d old events", len(deleted_event_ids))

    return {
        "stale_issue_ids": stale_issue_ids,
        "deleted_event_ids": deleted_event_ids,
        "issues_deleted": len(stale_issue_ids),
        "events_deleted": len(deleted_event_ids),
    }
