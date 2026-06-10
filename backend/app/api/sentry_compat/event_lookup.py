"""Shared event lookup for the Sentry-compat routes.

Sentry event IDs are 32-char dashless hex strings, which `uuid.UUID()`
happily parses — so routes must NOT branch on UUID-parseability to decide
which column to query. This helper matches both columns in one query.
"""
import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event


async def find_event(
    db: AsyncSession,
    raw_id: str,
    issue_id: uuid.UUID | None = None,
) -> Event | None:
    """Find an event by Sentry hex eventID or internal UUID primary key.

    Optionally scope the lookup to a single issue.
    """
    conds = [Event.event_id == raw_id]
    try:
        conds.append(Event.id == uuid.UUID(raw_id))
    except ValueError:
        pass

    q = select(Event).where(or_(*conds))
    if issue_id is not None:
        q = q.where(Event.issue_id == issue_id)

    result = await db.execute(q)
    return result.scalars().first()
