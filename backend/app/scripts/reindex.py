"""Full Meilisearch re-index script.

Usage:
    python -m app.scripts.reindex
"""
import asyncio
import sys

from sqlalchemy import select

from app.database import async_session_factory
from app.models.project import Project
from app.models.issue import Issue
from app.models.event import Event
from app.logging import setup_logging, get_logger

setup_logging()
logger = get_logger("scripts.reindex")


def get_client():
    """Create a Meilisearch client."""
    import meilisearch
    from app.config import settings

    return meilisearch.Client(
        settings.MEILISEARCH_URL,
        settings.MEILISEARCH_MASTER_KEY,
    )


async def reindex_all():
    """Re-index all projects, issues, and events into Meilisearch."""
    client = get_client()

    # Ensure indexes exist with correct settings
    for name in ("issues", "events", "projects"):
        try:
            client.create_index(name, {"primaryKey": "id"})
        except Exception:
            pass

    client.index("issues").update_filterable_attributes(["project_id", "status", "level"])
    client.index("issues").update_sortable_attributes(["last_seen", "event_count"])
    client.index("events").update_filterable_attributes(["project_id", "issue_id"])
    client.index("events").update_sortable_attributes(["timestamp"])
    client.index("projects").update_filterable_attributes(["id"])
    client.index("projects").update_sortable_attributes(["created_at"])

    logger.info("Meilisearch indexes configured")

    async with async_session_factory() as db:
        # ── Projects ──
        result = await db.execute(select(Project))
        projects = result.scalars().all()
        if projects:
            docs = [
                {
                    "id": str(p.id),
                    "name": p.name,
                    "slug": p.slug,
                    "platform": p.platform or "",
                    "created_at": p.created_at.isoformat() if p.created_at else "",
                }
                for p in projects
            ]
            client.index("projects").add_documents(docs, primary_key="id")
            logger.info("Indexed %d projects", len(docs))

        # ── Issues ──
        result = await db.execute(select(Issue))
        issues = result.scalars().all()
        if issues:
            docs = [
                {
                    "id": str(i.id),
                    "title": i.title,
                    "fingerprint": i.fingerprint,
                    "status": i.status.value,
                    "level": i.level.value,
                    "project_id": str(i.project_id),
                    "event_count": i.event_count,
                    "first_seen": i.first_seen.isoformat() if i.first_seen else "",
                    "last_seen": i.last_seen.isoformat() if i.last_seen else "",
                    "metadata": i.metadata_ or {},
                }
                for i in issues
            ]
            client.index("issues").add_documents(docs, primary_key="id")
            logger.info("Indexed %d issues", len(docs))

        # ── Events (batch to avoid memory issues) ──
        batch_size = 500
        offset = 0
        total_events = 0
        while True:
            result = await db.execute(
                select(Event).order_by(Event.received_at.desc()).offset(offset).limit(batch_size)
            )
            events = result.scalars().all()
            if not events:
                break

            docs = []
            for e in events:
                raw = e.data or {}
                # Extract searchable text
                parts = []
                msg = raw.get("message", "")
                if isinstance(msg, dict):
                    msg = msg.get("formatted", msg.get("message", ""))
                if msg:
                    parts.append(str(msg))
                for exc in raw.get("exception", {}).get("values", []):
                    parts.append(exc.get("type", ""))
                    parts.append(exc.get("value", ""))
                searchable = " ".join(filter(None, parts))[:5000]

                docs.append({
                    "id": str(e.id),
                    "event_id": e.event_id,
                    "issue_id": str(e.issue_id),
                    "project_id": str(e.project_id),
                    "timestamp": e.timestamp.isoformat() if e.timestamp else "",
                    "searchable_text": searchable,
                })

            client.index("events").add_documents(docs, primary_key="id")
            total_events += len(docs)
            offset += batch_size

        if total_events:
            logger.info("Indexed %d events", total_events)

    logger.info("Re-index complete!")


if __name__ == "__main__":
    asyncio.run(reindex_all())
