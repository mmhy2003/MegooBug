"""Sentry-compatible project endpoints under /api/0/."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import CurrentUser, get_user_project_ids, check_project_access
from app.models.project import Project
from app.models.issue import Issue, IssueStatus

router = APIRouter()


def _fmt_dt(dt: datetime | None) -> str | None:
    """Format a datetime to ISO 8601 with Z suffix for Sentry MCP Zod validation.

    The Sentry MCP uses z.string().datetime() which requires the 'Z' suffix
    (e.g. '2024-01-15T10:30:00.000Z'), not '+00:00'.
    """
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _build_permalink(issue: Issue) -> str:
    """Build a valid permalink URL for an issue."""
    base = settings.APP_URL.rstrip("/")
    return f"{base}/issues/{issue.id}"


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
    sort: str | None = None,
    limit: int = Query(default=25, le=100),
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

    q = (
        select(Issue)
        .where(Issue.project_id == project.id)
        .order_by(Issue.last_seen.desc())
        .limit(limit)
    )

    # Parse basic Sentry query syntax
    if query:
        if "is:unresolved" in query:
            q = q.where(Issue.status == IssueStatus.UNRESOLVED)
        elif "is:resolved" in query:
            q = q.where(Issue.status == IssueStatus.RESOLVED)
        elif "is:ignored" in query:
            q = q.where(Issue.status == IssueStatus.IGNORED)

    issues_result = await db.execute(q)
    issues = issues_result.scalars().all()
    return [_issue_to_sentry(i, project) for i in issues]


@router.get("/projects/{org}/{slug}/keys/")
async def list_project_keys(
    org: str,
    slug: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """List DSN keys for a project. Returns the project's single DSN key.

    Schema: ClientKeySchema requires:
    - id: z.union([z.string(), z.number()])
    - name: z.string()
    - dsn: { public: z.string() }
    - isActive: z.boolean()
    - dateCreated: z.string().datetime().nullable()  ← needs Z suffix
    """
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
    # Parse protocol for DSN format
    if "://" in base_url:
        protocol, host_part = base_url.split("://", 1)
    else:
        protocol, host_part = "https", base_url

    dsn_public = f"{protocol}://{project.dsn_public_key}@{host_part}/{project.id}"

    return [{
        "id": project.dsn_public_key,
        "name": "Default",
        "public": project.dsn_public_key,
        "secret": "",
        "projectId": str(project.id),
        "isActive": True,
        "dateCreated": _fmt_dt(project.created_at),
        "dsn": {
            "public": dsn_public,
            "secret": "",
            "csp": "",
        },
    }]


def _project_to_sentry(project: Project) -> dict:
    """Convert Project to Sentry-compatible JSON.

    Must include 'name' field — Sentry MCP validates with ProjectSchema
    which requires z.string() for name.
    """
    return {
        "id": str(project.id),
        "slug": project.slug,
        "name": project.name,
        "platform": project.platform or None,
        "dateCreated": _fmt_dt(project.created_at),
        "status": "active",
        "organization": {"id": "1", "slug": "megoobug", "name": settings.APP_NAME},
    }


def _issue_to_sentry(issue: Issue, project: Project | None = None) -> dict:
    """Convert Issue to Sentry-compatible JSON.

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
