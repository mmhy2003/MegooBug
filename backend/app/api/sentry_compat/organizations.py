"""Sentry-compatible organization endpoints.

MegooBug is single-organization. The {org} parameter is accepted but ignored.
"""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import CurrentUser, get_user_project_ids, check_project_access
from app.models.project import Project
from app.models.issue import Issue, IssueStatus
from app.models.event import Event
from app.models.user import User
from app.logging import get_logger

logger = get_logger("api.sentry_compat.organizations")

router = APIRouter()


def _fmt_dt(dt: datetime | None) -> str | None:
    """Format a datetime to ISO 8601 with Z suffix for Sentry MCP Zod validation.

    The Sentry MCP uses z.string().datetime() which requires the 'Z' suffix
    (e.g. '2024-01-15T10:30:00.000Z'), not '+00:00'.
    """
    if dt is None:
        return None
    # Ensure we output Z, not +00:00
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _build_permalink(issue: Issue) -> str:
    """Build a valid permalink URL for an issue.

    The Sentry MCP validates this with z.string().url() — empty strings fail.
    """
    base = settings.APP_URL.rstrip("/")
    return f"{base}/issues/{issue.id}"


def _org_response() -> dict:
    """Single org representation matching Sentry's format."""
    base = settings.APP_URL.rstrip("/")
    return {
        "id": "1",
        "slug": "megoobug",
        "name": settings.APP_NAME,
        "status": {"id": "active", "name": "active"},
        "isDefault": True,
        "links": {
            "regionUrl": "",
            "organizationUrl": base,
        },
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
    sort: str | None = None,
    limit: int = Query(default=25, le=100),
):
    """List issues across the organization. Non-admins see only issues from their projects."""
    q = select(Issue).order_by(Issue.last_seen.desc()).limit(limit)

    project_ids = await get_user_project_ids(current_user, db)
    if project_ids is not None:
        q = q.where(Issue.project_id.in_(project_ids))

    # Parse basic Sentry query syntax
    if query:
        if "is:unresolved" in query:
            q = q.where(Issue.status == IssueStatus.UNRESOLVED)
        elif "is:resolved" in query:
            q = q.where(Issue.status == IssueStatus.RESOLVED)
        elif "is:ignored" in query:
            q = q.where(Issue.status == IssueStatus.IGNORED)

    # Join project to get name/slug
    result = await db.execute(q)
    issues = result.scalars().all()

    # Prefetch project data for all issues
    project_id_set = {i.project_id for i in issues}
    if project_id_set:
        proj_result = await db.execute(
            select(Project).where(Project.id.in_(project_id_set))
        )
        proj_map = {p.id: p for p in proj_result.scalars().all()}
    else:
        proj_map = {}

    return [_issue_to_sentry(i, proj_map.get(i.project_id)) for i in issues]


@router.get("/organizations/{org}/releases/")
async def list_org_releases(
    org: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    query: str | None = None,
    per_page: int = Query(default=20, le=100),
):
    """List releases. MegooBug doesn't have native release tracking,
    so we synthesize releases from unique release values in event metadata."""
    # Return empty list — releases are not a MegooBug concept yet
    return []


@router.get("/organizations/{org}/events/")
async def list_org_events(
    org: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    dataset: str = "errors",
    field: list[str] | None = Query(default=None),
    query: str | None = None,
    sort: str | None = None,
    per_page: int = Query(default=10, le=100),
    statsPeriod: str | None = None,
    project: int | None = None,
):
    """Sentry-compatible events/discover endpoint.

    Supports the 'errors' dataset. Returns data in the format expected
    by the Sentry MCP's EventsResponseSchema.
    """
    from datetime import timedelta, timezone as tz

    # Default fields for errors dataset
    if not field:
        field = ["issue", "title", "project", "timestamp", "level", "message",
                 "error.type", "culprit"]

    # Determine if this is an aggregate query
    is_aggregate = any("(" in f for f in field)

    # Parse statsPeriod
    now = datetime.now(tz.utc)
    start_time = None
    if statsPeriod:
        unit = statsPeriod[-1]
        amount = int(statsPeriod[:-1])
        if unit == "h":
            start_time = now - timedelta(hours=amount)
        elif unit == "d":
            start_time = now - timedelta(days=amount)
        elif unit == "w":
            start_time = now - timedelta(weeks=amount)

    # Build base query
    project_ids = await get_user_project_ids(current_user, db)

    if is_aggregate and "count()" in field:
        # Aggregate query — group by issue
        q = select(
            Issue.id,
            Issue.title,
            Issue.event_count,
            Issue.last_seen,
            Issue.project_id,
        )

        if project_ids is not None:
            q = q.where(Issue.project_id.in_(project_ids))

        if project:
            # Need to resolve numeric project ID to UUID
            proj_result = await db.execute(
                select(Project).where(Project.project_number == project)
            )
            proj = proj_result.scalar_one_or_none()
            if proj:
                q = q.where(Issue.project_id == proj.id)

        if start_time:
            q = q.where(Issue.last_seen >= start_time)

        # Parse query filter for project slug
        if query and "project:" in query:
            import re
            match = re.search(r"project:(\S+)", query)
            if match:
                proj_slug = match.group(1)
                proj_result = await db.execute(
                    select(Project).where(Project.slug == proj_slug)
                )
                proj = proj_result.scalar_one_or_none()
                if proj:
                    q = q.where(Issue.project_id == proj.id)

        q = q.order_by(Issue.event_count.desc()).limit(per_page)
        result = await db.execute(q)
        rows = result.all()

        # Fetch project slugs
        pids = {r.project_id for r in rows}
        if pids:
            pr = await db.execute(select(Project).where(Project.id.in_(pids)))
            pm = {p.id: p for p in pr.scalars().all()}
        else:
            pm = {}

        data = []
        for row in rows:
            proj_obj = pm.get(row.project_id)
            data.append({
                "issue": str(row.id)[:8].upper(),
                "issue.id": str(row.id),
                "title": row.title,
                "project": proj_obj.slug if proj_obj else "",
                "count()": row.event_count,
                "last_seen()": _fmt_dt(row.last_seen) or "",
            })

        return {
            "data": data,
            "meta": {
                "fields": {f: "string" for f in field},
            },
        }
    else:
        # Individual events query
        q = (
            select(Event)
            .order_by(Event.timestamp.desc())
            .limit(per_page)
        )

        if project_ids is not None:
            q = q.where(Event.project_id.in_(project_ids))

        if start_time:
            q = q.where(Event.timestamp >= start_time)

        result = await db.execute(q)
        events = result.scalars().all()

        # Fetch project slugs
        pids = {e.project_id for e in events}
        if pids:
            pr = await db.execute(select(Project).where(Project.id.in_(pids)))
            pm = {p.id: p for p in pr.scalars().all()}
        else:
            pm = {}

        data = []
        for e in events:
            proj_obj = pm.get(e.project_id)
            ev_data = e.data or {}
            data.append({
                "id": str(e.id),
                "issue": str(e.issue_id)[:8].upper(),
                "issue.id": str(e.issue_id),
                "title": ev_data.get("message", ""),
                "project": proj_obj.slug if proj_obj else "",
                "timestamp": _fmt_dt(e.timestamp) or "",
                "level": ev_data.get("level", "error"),
                "message": ev_data.get("message", ""),
            })

        return {
            "data": data,
            "meta": {
                "fields": {f: "string" for f in field},
            },
        }


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


def _make_short_id(issue: Issue, project: Project | None = None) -> str:
    """Build a Sentry-format shortId like 'FILES-BACKEND-42'.

    The Sentry MCP SDK expects shortIds in the format PROJECT-ALPHANUMERIC.
    We use the project slug (uppercased) + issue_number.
    Falls back to truncated UUID hex if issue_number is not set yet.
    """
    slug_part = (project.slug if project else "UNKNOWN").upper()
    if issue.issue_number:
        return f"{slug_part}-{issue.issue_number}"
    # Fallback for issues created before the issue_number migration
    return f"{slug_part}-{str(issue.id).split('-')[0].upper()}"


def _issue_to_sentry(issue: Issue, project: Project | None = None) -> dict:
    """Convert Issue to Sentry-compatible JSON.

    Fixes for Sentry MCP Zod schema (IssueSchema):
    - shortId: Sentry format 'PROJECT-123' (not truncated UUID)
    - firstSeen/lastSeen: z.string().datetime().nullable() — needs Z suffix
    - userCount: z.union([z.string(), z.number()]) — required, was missing
    - permalink: z.string().url() — must be valid URL, not empty string
    - project: ProjectSchema — requires name field
    - culprit: z.string().nullable() — must be present
    """
    return {
        "id": str(issue.id),
        "shortId": _make_short_id(issue, project),
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
    """Convert Event to Sentry-compatible JSON for org-scoped endpoints."""
    data = event.data or {}
    return {
        "id": str(event.id),
        "eventID": event.event_id,
        "projectID": str(event.project_id),
        "groupID": str(event.issue_id),
        "title": data.get("message", ""),
        "message": data.get("message", ""),
        "type": "error",
        "platform": data.get("platform"),
        "culprit": None,
        "dateCreated": _fmt_dt(event.timestamp),
        "dateReceived": _fmt_dt(event.received_at),
        "contexts": data.get("contexts", {}),
        "context": {},
        "entries": _build_entries(data),
        "tags": _build_tags(data),
        "user": data.get("user"),
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


def _build_tags(data: dict) -> list:
    """Build Sentry-style tags array from raw event data."""
    raw_tags = data.get("tags")
    if isinstance(raw_tags, list):
        return raw_tags
    if isinstance(raw_tags, dict):
        return [{"key": k, "value": v} for k, v in raw_tags.items()]
    return []


# ── Auth endpoint (whoami) ──────────────────────────────────────────────

@router.get("/auth/")
async def get_authenticated_user(current_user: CurrentUser):
    """Sentry-compatible auth endpoint. Used by MCP's whoami tool.

    Schema: UserSchema requires:
    - id: z.union([z.string(), z.number()])
    - name: z.string().nullable()
    - email: z.string()
    """
    return {
        "id": str(current_user.id),
        "name": current_user.name,
        "email": current_user.email,
    }


# ── Org-scoped issue detail and events ──────────────────────────────────

@router.get("/organizations/{org}/issues/{issue_id}/")
async def get_org_issue(
    org: str,
    issue_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Get issue detail (org-scoped). Used by MCP's get_sentry_resource tool.

    The issue_id can be a UUID or a short ID.
    """
    issue = await _resolve_issue(issue_id, current_user, db)

    proj_result = await db.execute(
        select(Project).where(Project.id == issue.project_id)
    )
    project = proj_result.scalar_one_or_none()
    return _issue_to_sentry(issue, project)


@router.put("/organizations/{org}/issues/{issue_id}/")
async def update_org_issue(
    org: str,
    issue_id: str,
    body: dict,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Update issue (org-scoped). Used by MCP's update_issue tool."""
    issue = await _resolve_issue(issue_id, current_user, db)

    if "status" in body:
        status_map = {
            "resolved": IssueStatus.RESOLVED,
            "resolvedInNextRelease": IssueStatus.RESOLVED,
            "unresolved": IssueStatus.UNRESOLVED,
            "ignored": IssueStatus.IGNORED,
            "muted": IssueStatus.IGNORED,
        }
        new_status = status_map.get(body["status"])
        if new_status:
            issue.status = new_status
            logger.info("Issue %s status → %s via MCP", issue_id, new_status.value)

    await db.flush()
    await db.refresh(issue)

    proj_result = await db.execute(
        select(Project).where(Project.id == issue.project_id)
    )
    project = proj_result.scalar_one_or_none()
    return _issue_to_sentry(issue, project)


@router.get("/organizations/{org}/issues/{issue_id}/events/")
async def list_org_issue_events(
    org: str,
    issue_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    per_page: int = Query(default=50, le=100),
    full: bool = False,
):
    """List events for an issue (org-scoped). Used by MCP's list_issue_events tool."""
    issue = await _resolve_issue(issue_id, current_user, db)

    result = await db.execute(
        select(Event)
        .where(Event.issue_id == issue.id)
        .order_by(Event.timestamp.desc())
        .limit(per_page)
    )
    events = result.scalars().all()
    return [_event_to_sentry(e) for e in events]


@router.get("/organizations/{org}/issues/{issue_id}/events/latest/")
async def get_org_issue_latest_event(
    org: str,
    issue_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Get latest event for an issue (org-scoped). Used by MCP's getLatestEventForIssue."""
    issue = await _resolve_issue(issue_id, current_user, db)

    result = await db.execute(
        select(Event)
        .where(Event.issue_id == issue.id)
        .order_by(Event.timestamp.desc())
        .limit(1)
    )
    event = result.scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="No events found")
    return _event_to_sentry(event)


@router.get("/organizations/{org}/issues/{issue_id}/events/{event_id}/")
async def get_org_issue_event(
    org: str,
    issue_id: str,
    event_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific event for an issue (org-scoped). Used by MCP's getEventForIssue."""
    issue = await _resolve_issue(issue_id, current_user, db)

    if event_id == "latest":
        result = await db.execute(
            select(Event)
            .where(Event.issue_id == issue.id)
            .order_by(Event.timestamp.desc())
            .limit(1)
        )
    else:
        try:
            eid = UUID(event_id)
            result = await db.execute(
                select(Event).where(Event.id == eid, Event.issue_id == issue.id)
            )
        except ValueError:
            result = await db.execute(
                select(Event).where(
                    Event.event_id == event_id, Event.issue_id == issue.id
                )
            )

    event = result.scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return _event_to_sentry(event)


async def _resolve_issue(
    issue_id: str,
    current_user,
    db: AsyncSession,
) -> Issue:
    """Resolve an issue by UUID, numeric ID, or Sentry shortId.

    Supported formats:
    - Full UUID: '0dcae490-c3e2-4b5e-86b8-98e5f7e3ad10'
    - Numeric issue number: '42'
    - Sentry shortId: 'FILES-BACKEND-42'
    """
    issue = None

    # 1) Try full UUID
    try:
        uid = UUID(issue_id)
        result = await db.execute(select(Issue).where(Issue.id == uid))
        issue = result.scalar_one_or_none()
    except ValueError:
        pass

    # 2) Try numeric issue_number
    if issue is None and issue_id.isdigit():
        result = await db.execute(
            select(Issue).where(Issue.issue_number == int(issue_id))
        )
        issue = result.scalar_one_or_none()

    # 3) Try Sentry shortId format: 'PROJECT-SLUG-42'
    if issue is None and "-" in issue_id:
        # The numeric part is the last segment after the final hyphen
        parts = issue_id.rsplit("-", 1)
        if len(parts) == 2 and parts[1].isdigit():
            num = int(parts[1])
            result = await db.execute(
                select(Issue).where(Issue.issue_number == num)
            )
            issue = result.scalar_one_or_none()

    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    if not await check_project_access(current_user, issue.project_id, db):
        raise HTTPException(status_code=404, detail="Issue not found")
    return issue

