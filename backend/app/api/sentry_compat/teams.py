"""Sentry-compatible teams endpoints under /api/0/.

Supports the Sentry MCP tools:
- find_teams: GET /organizations/{org}/teams/
- create_team: POST /organizations/{org}/teams/
- get_team: GET /teams/{org}/{team_slug}/

TeamSchema requires:
  - id: z.union([z.string(), z.number()])
  - slug: z.string()
  - name: z.string()
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from slugify import slugify
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import CurrentUser
from app.models.team import Team, TeamMember, TeamRole
from app.models.project import Project, ProjectMember
from app.models.user import UserRole

import secrets

router = APIRouter()


def _fmt_dt(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _team_to_sentry(team: Team, member_count: int = 0) -> dict:
    """Convert Team to Sentry-compatible TeamSchema JSON."""
    return {
        "id": str(team.team_number),
        "slug": team.slug,
        "name": team.name,
        "dateCreated": _fmt_dt(team.created_at),
        "isMember": True,
        "memberCount": member_count,
        "avatar": {"avatarType": "letter_avatar"},
    }


@router.get("/organizations/{org}/teams/")
async def list_teams(
    org: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """List all teams. Used by MCP's find_teams tool."""
    member_count_subq = (
        select(func.count(TeamMember.user_id))
        .where(TeamMember.team_id == Team.id)
        .correlate(Team)
        .scalar_subquery()
        .label("member_count")
    )

    result = await db.execute(
        select(Team, member_count_subq).order_by(Team.created_at)
    )

    return [
        _team_to_sentry(team, mc or 0)
        for team, mc in result.all()
    ]


@router.post("/organizations/{org}/teams/")
async def create_team(
    org: str,
    body: dict,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Create a new team. Used by MCP's create_team tool.

    The MCP sends: {"name": "team-name"}
    """
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Team name is required")

    # Only admins can create teams
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin role required to create teams")

    # Generate unique slug
    base_slug = slugify(name)
    slug = base_slug
    counter = 1
    while True:
        existing = await db.execute(
            select(Team).where(Team.slug == slug)
        )
        if existing.scalar_one_or_none() is None:
            break
        slug = f"{base_slug}-{counter}"
        counter += 1

    team = Team(name=name, slug=slug)
    db.add(team)
    await db.flush()
    await db.refresh(team)

    # Auto-add creator as team admin
    member = TeamMember(
        team_id=team.id,
        user_id=current_user.id,
        role=TeamRole.ADMIN,
    )
    db.add(member)
    await db.flush()

    return _team_to_sentry(team, member_count=1)


@router.get("/teams/{org}/{team_slug}/")
async def get_team(
    org: str,
    team_slug: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Get team detail. Used by MCP's get_sentry_resource for team type."""
    result = await db.execute(
        select(Team).where(Team.slug == team_slug)
    )
    team = result.scalar_one_or_none()
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")

    mc_result = await db.execute(
        select(func.count(TeamMember.user_id)).where(TeamMember.team_id == team.id)
    )
    mc = mc_result.scalar() or 0

    resp = _team_to_sentry(team, mc)
    resp["organization"] = {
        "id": "1",
        "slug": "megoobug",
        "name": settings.APP_NAME,
    }
    return resp


@router.post("/teams/{org}/{team_slug}/projects/", status_code=201)
async def create_project_for_team(
    org: str,
    team_slug: str,
    body: dict,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Create a project under a team. Used by MCP's create_project tool.

    The MCP sends: {"name": "project-name", "platform": "python"}
    """
    # Only admins and developers can create projects
    if current_user.role not in (UserRole.ADMIN, UserRole.DEVELOPER):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    # Verify team exists
    team_result = await db.execute(
        select(Team).where(Team.slug == team_slug)
    )
    team = team_result.scalar_one_or_none()
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")

    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Project name is required")

    platform = body.get("platform")

    # Generate unique slug
    base_slug = slugify(name)
    slug = base_slug
    counter = 1
    while True:
        existing = await db.execute(
            select(Project).where(Project.slug == slug)
        )
        if existing.scalar_one_or_none() is None:
            break
        slug = f"{base_slug}-{counter}"
        counter += 1

    project = Project(
        name=name,
        slug=slug,
        platform=platform,
        dsn_public_key=secrets.token_hex(16),
        created_by=current_user.id,
        team_id=team.id,
    )
    db.add(project)
    await db.flush()
    await db.refresh(project)

    # Auto-add creator as project member
    member = ProjectMember(
        project_id=project.id,
        user_id=current_user.id,
    )
    db.add(member)
    await db.flush()

    # Build DSN for response
    base_url = settings.APP_URL.rstrip("/")
    if "://" in base_url:
        protocol, host_part = base_url.split("://", 1)
    else:
        protocol, host_part = "https", base_url

    dsn_public = f"{protocol}://{project.dsn_public_key}@{host_part}/{project.project_number}"

    return {
        "id": str(project.id),
        "slug": project.slug,
        "name": project.name,
        "platform": project.platform or None,
        "dateCreated": _fmt_dt(project.created_at),
        "status": "active",
        "organization": {"id": "1", "slug": "megoobug", "name": settings.APP_NAME},
        "team": _team_to_sentry(team),
        "teams": [_team_to_sentry(team)],
        "keys": [{
            "dsn": {"public": dsn_public},
        }],
    }
