from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import CurrentUser, require_developer_or_above, check_project_access
from app.models.project import Project
from app.models.issue import Issue, IssueStatus, IssueLevel
from app.models.event import Event
from app.models.user import User
from app.schemas.issue import IssueResponse, IssueUpdate, IssueListResponse
from app.schemas.event import EventResponse, EventListResponse
from app.logging import get_logger

logger = get_logger("api.issues")

router = APIRouter()


@router.get("/projects/{slug}/issues", response_model=IssueListResponse)
async def list_project_issues(
    slug: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    status_filter: IssueStatus | None = Query(None, alias="status"),
    level: IssueLevel | None = None,
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List issues for a project. Must be a member or admin."""
    result = await db.execute(
        select(Project).where(Project.slug == slug)
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not await check_project_access(current_user, project.id, db):
        raise HTTPException(status_code=404, detail="Project not found")

    query = select(Issue).where(Issue.project_id == project.id)
    count_query = select(func.count(Issue.id)).where(Issue.project_id == project.id)

    if status_filter is not None:
        query = query.where(Issue.status == status_filter)
        count_query = count_query.where(Issue.status == status_filter)
    if level is not None:
        query = query.where(Issue.level == level)
        count_query = count_query.where(Issue.level == level)

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    query = query.order_by(Issue.last_seen.desc()).limit(limit).offset(offset)
    issues_result = await db.execute(query)

    return IssueListResponse(
        items=issues_result.scalars().all(),
        total=total,
    )


@router.get("/issues/{issue_id}", response_model=IssueResponse)
async def get_issue(
    issue_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Get issue detail by ID. Must have access to the issue's project."""
    result = await db.execute(
        select(Issue).where(Issue.id == issue_id)
    )
    issue = result.scalar_one_or_none()
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    if not await check_project_access(current_user, issue.project_id, db):
        raise HTTPException(status_code=404, detail="Issue not found")
    return issue


@router.patch("/issues/{issue_id}", response_model=IssueResponse)
async def update_issue(
    issue_id: UUID,
    body: IssueUpdate,
    current_user: User = Depends(require_developer_or_above),
    db: AsyncSession = Depends(get_db),
):
    """Update issue status. Must have access to the issue's project."""
    result = await db.execute(
        select(Issue).where(Issue.id == issue_id)
    )
    issue = result.scalar_one_or_none()
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    if not await check_project_access(current_user, issue.project_id, db):
        raise HTTPException(status_code=404, detail="Issue not found")

    old_status = issue.status
    issue.status = body.status
    await db.flush()
    await db.refresh(issue)

    logger.info(
        "Issue %s status changed: %s → %s by %s",
        issue_id, old_status.value, body.status.value, current_user.email,
    )
    return issue


@router.get("/issues/{issue_id}/events", response_model=EventListResponse)
async def list_issue_events(
    issue_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List events for an issue. Must have access to the issue's project."""
    # Verify issue exists and check access
    issue_result = await db.execute(
        select(Issue).where(Issue.id == issue_id)
    )
    issue = issue_result.scalar_one_or_none()
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    if not await check_project_access(current_user, issue.project_id, db):
        raise HTTPException(status_code=404, detail="Issue not found")

    count_result = await db.execute(
        select(func.count(Event.id)).where(Event.issue_id == issue_id)
    )
    total = count_result.scalar()

    events_result = await db.execute(
        select(Event)
        .where(Event.issue_id == issue_id)
        .order_by(Event.timestamp.desc())
        .limit(limit).offset(offset)
    )

    return EventListResponse(
        items=events_result.scalars().all(),
        total=total,
    )


@router.get("/events/{event_id}", response_model=EventResponse)
async def get_event(
    event_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Get a single event by ID. Must have access to the event's project."""
    result = await db.execute(
        select(Event).where(Event.id == event_id)
    )
    event = result.scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    if not await check_project_access(current_user, event.project_id, db):
        raise HTTPException(status_code=404, detail="Event not found")
    return event
