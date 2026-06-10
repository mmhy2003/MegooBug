"""Retention cleanup: delete ingested data older than RETENTION_DAYS.

The async core (`_cleanup`) touches Postgres only and is unit-tested.
The Celery task wrapper and the Meilisearch mirror live in this module too
(added alongside) but stay out of the core so tests need neither Celery nor
Meilisearch.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.event import Event
from app.models.issue import Issue
from app.logging import get_logger
from app.worker import celery_app

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


async def _run_cleanup(cutoff: datetime) -> dict:
    """Run _cleanup with a fresh engine — the app's global engine must not
    cross the Celery worker process boundary."""
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as db:
            return await _cleanup(db, cutoff)
    finally:
        await engine.dispose()


def _mirror_to_meilisearch(summary: dict) -> None:
    """Best-effort removal of deleted rows from the search indexes.

    Failures are logged and swallowed (same pattern as the indexing tasks);
    a later reindex_all self-heals search.
    """
    try:
        import meilisearch

        client = meilisearch.Client(
            settings.MEILISEARCH_URL,
            settings.MEILISEARCH_MASTER_KEY,
        )

        stale_ids = [str(i) for i in summary["stale_issue_ids"]]
        if stale_ids:
            client.index("issues").delete_documents(stale_ids)
            # Events of stale issues were cascade-deleted in Postgres without
            # RETURNING; remove them from search by filter (issue_id is filterable).
            quoted = ", ".join(f'"{i}"' for i in stale_ids)
            client.index("events").delete_documents(filter=f"issue_id IN [{quoted}]")

        event_ids = [str(e) for e in summary["deleted_event_ids"]]
        if event_ids:
            client.index("events").delete_documents(event_ids)
    except Exception as e:
        logger.error("Retention: Meilisearch mirror failed (search will self-heal on reindex): %s", e)


@celery_app.task(name="cleanup_old_data")
def cleanup_old_data() -> dict:
    """Nightly retention: drop ingested data older than RETENTION_DAYS."""
    if settings.RETENTION_DAYS <= 0:
        logger.info("Retention disabled (RETENTION_DAYS=%s), skipping", settings.RETENTION_DAYS)
        return {"issues_deleted": 0, "events_deleted": 0, "skipped": True}

    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.RETENTION_DAYS)
    summary = asyncio.run(_run_cleanup(cutoff))
    _mirror_to_meilisearch(summary)

    logger.info(
        "Retention run complete: %d issues, %d events deleted (cutoff %s)",
        summary["issues_deleted"], summary["events_deleted"], cutoff.isoformat(),
    )
    return {
        "issues_deleted": summary["issues_deleted"],
        "events_deleted": summary["events_deleted"],
    }
