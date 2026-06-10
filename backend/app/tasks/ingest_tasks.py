"""Celery task for asynchronous event ingestion.

The ingest API endpoints accept-and-enqueue; this task does the actual
processing (dedup, issue upsert, event insert, notifications, indexing)
by calling the existing async process_event.

PERSISTENT LOOP + ENGINE PER WORKER CHILD (load-bearing, non-obvious):
process_event is async but Celery tasks are sync. Creating an asyncpg
engine per task cannot sustain hundreds of events/sec, and an asyncpg
pool is bound to the event loop it was created on. So each prefork
worker child lazily creates ONE event loop, ONE async engine, and the
pubsub Redis pool (for websocket pushes inside process_event), and
reuses them for every task via loop.run_until_complete.
"""
import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.worker import celery_app
from app.config import settings
from app.logging import get_logger

logger = get_logger("tasks.ingest")

_loop: asyncio.AbstractEventLoop | None = None
_session_factory = None


def _get_loop_and_factory():
    """Lazily create the per-process loop, engine, and pubsub pool."""
    global _loop, _session_factory
    if _loop is None:
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        engine = create_async_engine(
            settings.DATABASE_URL, pool_size=5, max_overflow=2, pool_pre_ping=True
        )
        _session_factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        # process_event publishes websocket updates via the pubsub pool;
        # initialise it on this loop so realtime updates keep working.
        from app.services.pubsub import init_redis
        try:
            _loop.run_until_complete(init_redis())
        except Exception as e:
            logger.warning("Pubsub init failed in ingest worker (realtime updates off): %s", e)
    return _loop, _session_factory


def _reset_state() -> None:
    """Test hook: drop the cached loop/engine so a new DATABASE_URL takes effect."""
    global _loop, _session_factory
    if _loop is not None:
        try:
            _loop.close()
        except Exception:
            pass
    _loop = None
    _session_factory = None


async def _process(project_id: str, event_data: dict, session_factory) -> str | None:
    from app.models.project import Project
    from app.services.ingest import process_event

    async with session_factory() as db:
        result = await db.execute(
            select(Project).where(Project.id == uuid.UUID(project_id))
        )
        project = result.scalar_one_or_none()
        if project is None:
            logger.warning("Ingest: project %s no longer exists — dropping event", project_id)
            return None
        issue, event = await process_event(project, event_data, db)
        await db.commit()
        return event.event_id


@celery_app.task(name="ingest_event")
def ingest_event(project_id: str, event_data: dict) -> str | None:
    """Process one queued event. Fire-once: failures are logged and dropped."""
    loop, factory = _get_loop_and_factory()
    try:
        return loop.run_until_complete(_process(project_id, event_data, factory))
    except Exception:
        logger.error(
            "Failed to process event %s (project=%s)",
            event_data.get("event_id"), project_id, exc_info=True,
        )
        return None
