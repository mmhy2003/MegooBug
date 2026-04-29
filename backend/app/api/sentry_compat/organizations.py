"""Sentry-compatible organization endpoints.

MegooBug is single-organization. The {org} parameter is accepted but ignored.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import CurrentUser, get_user_project_ids
from app.models.project import Project
from app.models.issue import Issue
from app.models.user import User

router = APIRouter()


def _org_response() -> dict:
    """Single org representation matching Sentry's format."""
    return {
        "id": "1",
        "slug": "megoobug",
        "name": settings.APP_NAME,
        "status": {"id": "active", "name": "active"},
        "isDefault": True,
    }


@router.get("/")
async def api_index(current_user: CurrentUser):
    """API index — server info."""
    return {
        "version": "0.1.0",
        "app": settings.APP_NAME,
        "user": {
            "id": str(current_user.id),
            "name": current_user.name,
            "email": current_user.email,
        },
    }


@router.get("/organizations/")
async def list_organizations(current_user: CurrentUser):
    """List organizations. Returns single org (MegooBug is single-org)."""
    return [_org_response()]


@router.get("/organizations/{org}/")
async def get_organization(org: str, current_user: CurrentUser):
    """Get organization detail. Org slug is ignored."""
    return _org_response()


@router.get("/organizations/{org}/projects/")
async def list_org_projects(
    org: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """List projects for the organization. Non-admins see only their assigned projects."""
    query = select(Project).order_by(Project.created_at.desc())

    project_ids = await get_user_project_ids(current_user, db)
    if project_ids is not None:
        query = query.where(Project.id.in_(project_ids))

    result = await db.execute(query)
    projects = result.scalars().all()
    return [_project_to_sentry(p) for p in projects]


@router.get("/organizations/{org}/issues/")
async def list_org_issues(
    org: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    query: str | None = None,
    cursor: str | None = None,
):
    """List issues across the organization. Non-admins see only issues from their projects."""
    q = select(Issue).order_by(Issue.last_seen.desc()).limit(25)

    project_ids = await get_user_project_ids(current_user, db)
    if project_ids is not None:
        q = q.where(Issue.project_id.in_(project_ids))

    result = await db.execute(q)
    issues = result.scalars().all()
    return [_issue_to_sentry(i) for i in issues]


def _project_to_sentry(project: Project) -> dict:
    """Convert Project to Sentry-compatible JSON."""
    return {
        "id": str(project.id),
        "slug": project.slug,
        "name": project.name,
        "platform": project.platform or "",
        "dateCreated": project.created_at.isoformat() if project.created_at else "",
        "status": "active",
        "organization": {"id": "1", "slug": "megoobug", "name": settings.APP_NAME},
    }


def _issue_to_sentry(issue: Issue) -> dict:
    """Convert Issue to Sentry-compatible JSON."""
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
    }
