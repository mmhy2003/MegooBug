"""Teams management API endpoints."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from slugify import slugify
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import CurrentUser, require_admin
from app.models.team import Team, TeamMember, TeamRole
from app.models.project import Project
from app.models.user import User
from app.schemas.team import (
    TeamCreate, TeamUpdate, TeamResponse,
    TeamMemberAdd, TeamMemberResponse,
)
from app.logging import get_logger

logger = get_logger("api.teams")

router = APIRouter()


def _team_response(team: Team, member_count: int = 0, project_count: int = 0) -> dict:
    """Build team response dict."""
    return {
        "id": str(team.id),
        "team_number": team.team_number,
        "name": team.name,
        "slug": team.slug,
        "created_at": team.created_at.isoformat() if team.created_at else None,
        "member_count": member_count,
        "project_count": project_count,
    }


@router.get("", response_model=list[dict])
async def list_teams(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """List all teams with member and project counts."""
    member_count_subq = (
        select(func.count(TeamMember.user_id))
        .where(TeamMember.team_id == Team.id)
        .correlate(Team)
        .scalar_subquery()
        .label("member_count")
    )
    project_count_subq = (
        select(func.count(Project.id))
        .where(Project.team_id == Team.id)
        .correlate(Team)
        .scalar_subquery()
        .label("project_count")
    )

    result = await db.execute(
        select(Team, member_count_subq, project_count_subq)
        .order_by(Team.created_at)
    )

    return [
        _team_response(team, mc or 0, pc or 0)
        for team, mc, pc in result.all()
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_team(
    body: TeamCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new team. Admin only."""
    # Generate unique slug
    base_slug = slugify(body.name)
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

    team = Team(name=body.name, slug=slug)
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

    logger.info("Team created: %s (slug=%s) by %s", team.name, team.slug, current_user.email)
    return _team_response(team, member_count=1, project_count=0)


@router.get("/{slug}")
async def get_team(
    slug: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Get team detail by slug."""
    result = await db.execute(
        select(Team).where(Team.slug == slug)
    )
    team = result.scalar_one_or_none()
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")

    mc = await db.execute(
        select(func.count(TeamMember.user_id)).where(TeamMember.team_id == team.id)
    )
    pc = await db.execute(
        select(func.count(Project.id)).where(Project.team_id == team.id)
    )

    return _team_response(team, mc.scalar() or 0, pc.scalar() or 0)


@router.patch("/{slug}")
async def update_team(
    slug: str,
    body: TeamUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update a team. Admin only."""
    result = await db.execute(
        select(Team).where(Team.slug == slug)
    )
    team = result.scalar_one_or_none()
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")

    if body.name is not None:
        team.name = body.name
        # Update slug too
        base_slug = slugify(body.name)
        new_slug = base_slug
        counter = 1
        while True:
            existing = await db.execute(
                select(Team).where(Team.slug == new_slug, Team.id != team.id)
            )
            if existing.scalar_one_or_none() is None:
                break
            new_slug = f"{base_slug}-{counter}"
            counter += 1
        team.slug = new_slug

    await db.flush()
    await db.refresh(team)
    return _team_response(team)


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(
    slug: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a team. Admin only. Unassigns projects but does not delete them."""
    result = await db.execute(
        select(Team).where(Team.slug == slug)
    )
    team = result.scalar_one_or_none()
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")

    # Unassign projects from this team
    projects = await db.execute(
        select(Project).where(Project.team_id == team.id)
    )
    for project in projects.scalars().all():
        project.team_id = None

    await db.delete(team)
    logger.info("Team deleted: %s by %s", slug, current_user.email)


# ── Team Members ─────────────────────────────────────────────────────────


@router.get("/{slug}/members", response_model=list[TeamMemberResponse])
async def list_team_members(
    slug: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """List members of a team."""
    result = await db.execute(
        select(Team).where(Team.slug == slug)
    )
    team = result.scalar_one_or_none()
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")

    members_result = await db.execute(
        select(TeamMember, User)
        .join(User, TeamMember.user_id == User.id)
        .where(TeamMember.team_id == team.id)
    )

    return [
        TeamMemberResponse(
            user_id=user.id,
            user_name=user.name,
            user_email=user.email,
            user_role=user.role.value,
            team_role=tm.role.value,
            joined_at=tm.joined_at,
        )
        for tm, user in members_result.all()
    ]


@router.post("/{slug}/members", status_code=status.HTTP_201_CREATED)
async def add_team_member(
    slug: str,
    body: TeamMemberAdd,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Add a member to a team. Admin only."""
    result = await db.execute(
        select(Team).where(Team.slug == slug)
    )
    team = result.scalar_one_or_none()
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")

    # Verify user exists
    user_result = await db.execute(
        select(User).where(User.id == body.user_id)
    )
    user = user_result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Check not already a member
    existing = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team.id,
            TeamMember.user_id == body.user_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="User is already a team member")

    role = TeamRole.ADMIN if body.role == "admin" else TeamRole.MEMBER

    member = TeamMember(
        team_id=team.id,
        user_id=body.user_id,
        role=role,
    )
    db.add(member)
    await db.flush()

    logger.info("Added %s to team %s (role=%s)", user.email, team.slug, role.value)

    return TeamMemberResponse(
        user_id=user.id,
        user_name=user.name,
        user_email=user.email,
        user_role=user.role.value,
        team_role=member.role.value,
        joined_at=member.joined_at,
    )


@router.delete("/{slug}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_team_member(
    slug: str,
    user_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Remove a member from a team. Admin only."""
    result = await db.execute(
        select(Team).where(Team.slug == slug)
    )
    team = result.scalar_one_or_none()
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")

    member_result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team.id,
            TeamMember.user_id == user_id,
        )
    )
    member = member_result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")

    await db.delete(member)
    logger.info("Removed user %s from team %s", user_id, team.slug)
