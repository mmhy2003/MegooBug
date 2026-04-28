"""Dashboard stats and trend data endpoints."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import CurrentUser
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
    """Get aggregated dashboard stats."""
    now = datetime.now(timezone.utc)
    last_24h = now - timedelta(hours=24)

    # Total projects
    projects_count = await db.execute(select(func.count(Project.id)))

    # Errors in last 24h (events received)
    errors_24h = await db.execute(
        select(func.count(Event.id)).where(Event.received_at >= last_24h)
    )

    # Unresolved issues
    unresolved = await db.execute(
        select(func.count(Issue.id)).where(Issue.status == IssueStatus.UNRESOLVED)
    )

    # Active users (users who have at least one project membership)
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
    """Get error trend data for a project (daily event counts)."""
    result = await db.execute(
        select(Project).where(Project.slug == slug)
    )
    project = result.scalar_one_or_none()
    if project is None:
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
