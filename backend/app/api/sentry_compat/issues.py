"""Sentry-compatible issue and event endpoints under /api/0/."""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import CurrentUser, check_project_access
from app.models.issue import Issue, IssueStatus
from app.models.event import Event
from app.models.project import Project
from app.logging import get_logger

logger = get_logger("api.sentry_compat.issues")

router = APIRouter()


def _fmt_dt(dt: datetime | None) -> str | None:
    """Format a datetime to ISO 8601 with Z suffix for Sentry MCP Zod validation."""
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _build_permalink(issue: Issue) -> str:
    """Build a valid permalink URL for an issue."""
    base = settings.APP_URL.rstrip("/")
    return f"{base}/issues/{issue.id}"


@router.get("/issues/{issue_id}/")
async def get_issue(
    issue_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Get issue detail in Sentry-compatible format."""
    result = await db.execute(
        select(Issue).where(Issue.id == issue_id)
    )
    issue = result.scalar_one_or_none()
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    if not await check_project_access(current_user, issue.project_id, db):
        raise HTTPException(status_code=404, detail="Issue not found")

    # Fetch project for name/slug
    proj_result = await db.execute(
        select(Project).where(Project.id == issue.project_id)
    )
    project = proj_result.scalar_one_or_none()

    return _issue_detail_to_sentry(issue, project)


@router.put("/issues/{issue_id}/")
async def update_issue(
    issue_id: UUID,
    body: dict,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Update issue (status, assignee, etc.) in Sentry-compatible format."""
    result = await db.execute(
        select(Issue).where(Issue.id == issue_id)
    )
    issue = result.scalar_one_or_none()
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    if not await check_project_access(current_user, issue.project_id, db):
        raise HTTPException(status_code=404, detail="Issue not found")

    # Handle status updates
    if "status" in body:
        status_map = {
            "resolved": IssueStatus.RESOLVED,
            "unresolved": IssueStatus.UNRESOLVED,
            "ignored": IssueStatus.IGNORED,
            "muted": IssueStatus.IGNORED,
        }
        new_status = status_map.get(body["status"])
        if new_status:
            issue.status = new_status
            logger.info("Issue %s status updated to %s via compat API", issue_id, new_status.value)

    await db.flush()
    await db.refresh(issue)

    # Fetch project for name/slug
    proj_result = await db.execute(
        select(Project).where(Project.id == issue.project_id)
    )
    project = proj_result.scalar_one_or_none()

    return _issue_detail_to_sentry(issue, project)


@router.get("/issues/{issue_id}/events/")
async def list_issue_events(
    issue_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=25, le=100),
):
    """List events for an issue in Sentry-compatible format."""
    result = await db.execute(
        select(Issue).where(Issue.id == issue_id)
    )
    issue = result.scalar_one_or_none()
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    if not await check_project_access(current_user, issue.project_id, db):
        raise HTTPException(status_code=404, detail="Issue not found")

    events_result = await db.execute(
        select(Event)
        .where(Event.issue_id == issue_id)
        .order_by(Event.timestamp.desc())
        .limit(limit)
    )
    events = events_result.scalars().all()
    return [_event_to_sentry(e) for e in events]


@router.get("/issues/{issue_id}/events/latest/")
async def get_latest_event(
    issue_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Get the latest event for an issue."""
    result = await db.execute(
        select(Event)
        .where(Event.issue_id == issue_id)
        .order_by(Event.timestamp.desc())
        .limit(1)
    )
    event = result.scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="No events found")
    if not await check_project_access(current_user, event.project_id, db):
        raise HTTPException(status_code=404, detail="No events found")
    return _event_to_sentry(event)


@router.get("/events/{event_id}/")
async def get_event(
    event_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Get a single event by its internal ID."""
    result = await db.execute(
        select(Event).where(Event.id == event_id)
    )
    event = result.scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    if not await check_project_access(current_user, event.project_id, db):
        raise HTTPException(status_code=404, detail="Event not found")
    return _event_to_sentry(event)


def _issue_detail_to_sentry(issue: Issue, project: Project | None = None) -> dict:
    """Convert Issue to Sentry-compatible detail JSON.

    Fixes for Sentry MCP Zod schema (IssueSchema):
    - firstSeen/lastSeen: z.string().datetime().nullable() — needs Z suffix
    - userCount: z.union([z.string(), z.number()]) — required, was missing
    - permalink: z.string().url() — must be valid URL, not empty string
    - project: ProjectSchema — requires name field
    - culprit: z.string().nullable() — must be present
    """
    return {
        "id": str(issue.id),
        "shortId": str(issue.id)[:8].upper(),
        "title": issue.title,
        "culprit": None,
        "permalink": _build_permalink(issue),
        "level": issue.level.value if issue.level else "error",
        "status": issue.status.value if issue.status else "unresolved",
        "firstSeen": _fmt_dt(issue.first_seen),
        "lastSeen": _fmt_dt(issue.last_seen),
        "count": str(issue.event_count),
        "userCount": 0,
        "type": "error",
        "project": {
            "id": str(issue.project_id),
            "slug": project.slug if project else "",
            "name": project.name if project else "Unknown",
            "platform": (project.platform or None) if project else None,
        },
        "metadata": issue.metadata_ or {},
        "annotations": [],
        "isPublic": False,
        "hasSeen": False,
        "isBookmarked": False,
        "isSubscribed": False,
    }


def _event_to_sentry(event: Event) -> dict:
    """Convert Event to Sentry-compatible JSON.

    Uses Z-suffixed datetimes to pass Sentry MCP's z.string().datetime() validation.
    """
    data = event.data or {}
    return {
        "id": str(event.id),
        "eventID": event.event_id,
        "projectID": str(event.project_id),
        "groupID": str(event.issue_id),
        "title": data.get("message", ""),
        "message": data.get("message", ""),
        "dateCreated": _fmt_dt(event.timestamp),
        "dateReceived": _fmt_dt(event.received_at),
        "context": data.get("contexts", {}),
        "entries": _build_entries(data),
        "tags": data.get("tags", []),
        "sdk": data.get("sdk", {}),
    }


def _build_entries(data: dict) -> list:
    """Build Sentry-style entries array from raw event data."""
    entries = []

    # Exception entry
    exception = data.get("exception")
    if exception:
        entries.append({"type": "exception", "data": exception})

    # Breadcrumbs entry
    breadcrumbs = data.get("breadcrumbs")
    if breadcrumbs:
        entries.append({"type": "breadcrumbs", "data": breadcrumbs})

    # Request entry
    request = data.get("request")
    if request:
        entries.append({"type": "request", "data": request})

    return entries
