"""Dashboard stats and trend data endpoints."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import CurrentUser, get_user_project_ids, check_project_access
from app.models.project import Project
from app.models.issue import Issue, IssueStatus
from app.models.event import Event
from app.models.user import User

router = APIRouter()


@router.get("/stats/dashboard")
async def dashboard_stats(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Get aggregated dashboard stats. Non-admins see only their assigned projects."""
    now = datetime.now(timezone.utc)
    last_24h = now - timedelta(hours=24)

    # Get user's project scope
    project_ids = await get_user_project_ids(current_user, db)

    # Total projects
    projects_query = select(func.count(Project.id))
    if project_ids is not None:
        projects_query = projects_query.where(Project.id.in_(project_ids))
    projects_count = await db.execute(projects_query)

    # Errors in last 24h (events received)
    errors_query = select(func.count(Event.id)).where(Event.received_at >= last_24h)
    if project_ids is not None:
        errors_query = errors_query.where(Event.project_id.in_(project_ids))
    errors_24h = await db.execute(errors_query)

    # Unresolved issues
    unresolved_query = select(func.count(Issue.id)).where(Issue.status == IssueStatus.UNRESOLVED)
    if project_ids is not None:
        unresolved_query = unresolved_query.where(Issue.project_id.in_(project_ids))
    unresolved = await db.execute(unresolved_query)

    # Active users (global count — not scoped)
    active_users = await db.execute(
        select(func.count(User.id)).where(User.is_active == True)
    )

    return {
        "total_projects": projects_count.scalar() or 0,
        "errors_24h": errors_24h.scalar() or 0,
        "unresolved_issues": unresolved.scalar() or 0,
        "active_users": active_users.scalar() or 0,
    }


@router.get("/stats/projects/{slug}/trends")
async def project_trends(
    slug: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    days: int = 7,
):
    """Get error trend data for a project. Must be a member or admin."""
    result = await db.execute(
        select(Project).where(Project.slug == slug)
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not await check_project_access(current_user, project.id, db):
        raise HTTPException(status_code=404, detail="Project not found")

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)

    # Get daily event counts using date_trunc
    day_col = func.date_trunc("day", Event.received_at).label("day")
    trend_query = (
        select(
            day_col,
            func.count(Event.id).label("count"),
        )
        .where(
            Event.project_id == project.id,
            Event.received_at >= start,
        )
        .group_by(day_col)
        .order_by(day_col)
    )
    trend_result = await db.execute(trend_query)

    # Build day-by-day data (fill gaps with 0)
    trend_map = {row.day.date(): row.count for row in trend_result}
    data = []
    for i in range(days):
        day = (start + timedelta(days=i + 1)).date()
        data.append({
            "date": day.isoformat(),
            "count": trend_map.get(day, 0),
        })

    return {
        "project": slug,
        "days": days,
        "data": data,
    }
