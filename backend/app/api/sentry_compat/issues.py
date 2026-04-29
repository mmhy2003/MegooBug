"""Sentry-compatible issue and event endpoints under /api/0/."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import CurrentUser, check_project_access
from app.models.issue import Issue, IssueStatus
from app.models.event import Event
from app.logging import get_logger

logger = get_logger("api.sentry_compat.issues")

router = APIRouter()


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
    return _issue_detail_to_sentry(issue)


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
    return _issue_detail_to_sentry(issue)


@router.get("/issues/{issue_id}/events/")
async def list_issue_events(
    issue_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
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
        .limit(25)
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


def _issue_detail_to_sentry(issue: Issue) -> dict:
    """Convert Issue to Sentry-compatible detail JSON."""
    return {
        "id": str(issue.id),
        "shortId": str(issue.id)[:8],
        "title": issue.title,
        "culprit": "",
        "permalink": "",
        "level": issue.level.value if issue.level else "error",
        "status": issue.status.value if issue.status else "unresolved",
        "firstSeen": issue.first_seen.isoformat() if issue.first_seen else "",
        "lastSeen": issue.last_seen.isoformat() if issue.last_seen else "",
        "count": str(issue.event_count),
        "project": {"id": str(issue.project_id), "slug": ""},
        "metadata": issue.metadata_ or {},
        "type": "error",
        "annotations": [],
        "isPublic": False,
        "hasSeen": False,
        "isBookmarked": False,
        "isSubscribed": False,
    }


def _event_to_sentry(event: Event) -> dict:
    """Convert Event to Sentry-compatible JSON."""
    data = event.data or {}
    return {
        "id": str(event.id),
        "eventID": event.event_id,
        "projectID": str(event.project_id),
        "groupID": str(event.issue_id),
        "title": data.get("message", ""),
        "message": data.get("message", ""),
        "dateCreated": event.timestamp.isoformat() if event.timestamp else "",
        "dateReceived": event.received_at.isoformat() if event.received_at else "",
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
