"""Sentry-compatible project endpoints under /api/0/."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import CurrentUser, get_user_project_ids, check_project_access
from app.models.project import Project
from app.models.issue import Issue

router = APIRouter()


@router.get("/projects/")
async def list_projects(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """List projects (flat, no org scoping). Non-admins see only their assigned projects."""
    query = select(Project).order_by(Project.created_at.desc())

    project_ids = await get_user_project_ids(current_user, db)
    if project_ids is not None:
        query = query.where(Project.id.in_(project_ids))

    result = await db.execute(query)
    projects = result.scalars().all()
    return [_project_to_sentry(p) for p in projects]


@router.get("/projects/{org}/{slug}/")
async def get_project(
    org: str,
    slug: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Get project detail. Org param is ignored. Must be a member or admin."""
    result = await db.execute(
        select(Project).where(Project.slug == slug)
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not await check_project_access(current_user, project.id, db):
        raise HTTPException(status_code=404, detail="Project not found")
    return _project_to_sentry(project)


@router.get("/projects/{org}/{slug}/issues/")
async def list_project_issues(
    org: str,
    slug: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    query: str | None = None,
):
    """List issues for a specific project."""
    result = await db.execute(
        select(Project).where(Project.slug == slug)
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not await check_project_access(current_user, project.id, db):
        raise HTTPException(status_code=404, detail="Project not found")

    issues_result = await db.execute(
        select(Issue)
        .where(Issue.project_id == project.id)
        .order_by(Issue.last_seen.desc())
        .limit(25)
    )
    issues = issues_result.scalars().all()
    return [_issue_to_sentry(i) for i in issues]


@router.get("/projects/{org}/{slug}/keys/")
async def list_project_keys(
    org: str,
    slug: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """List DSN keys for a project. Returns the project's single DSN key."""
    result = await db.execute(
        select(Project).where(Project.slug == slug)
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not await check_project_access(current_user, project.id, db):
        raise HTTPException(status_code=404, detail="Project not found")

    # Build DSN URL
    base_url = settings.APP_URL.rstrip("/")
    dsn = f"{base_url}/api/{project.id}"

    return [{
        "id": project.dsn_public_key,
        "name": "Default",
        "public": project.dsn_public_key,
        "secret": "",
        "projectId": str(project.id),
        "isActive": True,
        "dateCreated": project.created_at.isoformat() if project.created_at else "",
        "dsn": {
            "public": f"{base_url.replace('http://', 'http://').replace('https://', 'https://')}"
                      f"/{project.dsn_public_key}@{base_url.split('://', 1)[-1]}/api/{project.id}",
            "secret": "",
            "csp": "",
        },
    }]


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
