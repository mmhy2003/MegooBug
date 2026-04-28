import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from slugify import slugify
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import CurrentUser, require_admin, require_developer_or_above
from app.models.project import Project, ProjectMember
from app.models.user import User
from app.schemas.project import (
    ProjectCreate, ProjectUpdate, ProjectResponse,
    ProjectMemberAdd, ProjectMemberResponse,
)
from app.logging import get_logger
from app.tasks.event_tasks import index_project_to_meilisearch

logger = get_logger("api.projects")

router = APIRouter()


def _generate_dsn_key() -> str:
    """Generate a unique DSN public key for a project."""
    return secrets.token_hex(16)


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """List all projects."""
    result = await db.execute(
        select(Project).order_by(Project.created_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    current_user: User = Depends(require_developer_or_above),
    db: AsyncSession = Depends(get_db),
):
    """Create a new project. Admin or Developer required."""
    # Generate unique slug
    base_slug = slugify(body.name)
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
        name=body.name,
        slug=slug,
        platform=body.platform,
        dsn_public_key=_generate_dsn_key(),
        created_by=current_user.id,
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

    logger.info("Project created: %s (slug=%s) by %s", project.name, project.slug, current_user.email)

    # Index in Meilisearch
    index_project_to_meilisearch.delay({
        "id": str(project.id),
        "name": project.name,
        "slug": project.slug,
        "platform": project.platform or "",
        "created_at": project.created_at.isoformat() if project.created_at else "",
    })

    return project


@router.get("/{slug}", response_model=ProjectResponse)
async def get_project(
    slug: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Get project details by slug."""
    result = await db.execute(
        select(Project).where(Project.slug == slug)
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/{slug}", response_model=ProjectResponse)
async def update_project(
    slug: str,
    body: ProjectUpdate,
    current_user: User = Depends(require_developer_or_above),
    db: AsyncSession = Depends(get_db),
):
    """Update a project. Admin or Developer required."""
    result = await db.execute(
        select(Project).where(Project.slug == slug)
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    if body.name is not None:
        project.name = body.name
    if body.platform is not None:
        project.platform = body.platform

    await db.flush()
    await db.refresh(project)

    # Re-index in Meilisearch
    index_project_to_meilisearch.delay({
        "id": str(project.id),
        "name": project.name,
        "slug": project.slug,
        "platform": project.platform or "",
        "created_at": project.created_at.isoformat() if project.created_at else "",
    })

    return project


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    slug: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a project. Admin only."""
    result = await db.execute(
        select(Project).where(Project.slug == slug)
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    await db.delete(project)
    logger.info("Project deleted: %s by %s", slug, current_user.email)


@router.get("/{slug}/members", response_model=list[ProjectMemberResponse])
async def list_members(
    slug: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """List members of a project."""
    result = await db.execute(
        select(Project).where(Project.slug == slug)
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    members_result = await db.execute(
        select(ProjectMember, User)
        .join(User, ProjectMember.user_id == User.id)
        .where(ProjectMember.project_id == project.id)
    )

    members = []
    for pm, user in members_result.all():
        members.append(ProjectMemberResponse(
            user_id=user.id,
            user_name=user.name,
            user_email=user.email,
            user_role=user.role.value,
            notify_email=pm.notify_email,
            notify_inapp=pm.notify_inapp,
            joined_at=pm.joined_at,
        ))
    return members


@router.post("/{slug}/members", response_model=ProjectMemberResponse, status_code=status.HTTP_201_CREATED)
async def add_member(
    slug: str,
    body: ProjectMemberAdd,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Add a member to a project. Admin only."""
    result = await db.execute(
        select(Project).where(Project.slug == slug)
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check user exists
    user_result = await db.execute(
        select(User).where(User.id == body.user_id)
    )
    user = user_result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Check not already a member
    existing = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == body.user_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="User is already a member")

    member = ProjectMember(
        project_id=project.id,
        user_id=body.user_id,
        notify_email=body.notify_email,
        notify_inapp=body.notify_inapp,
    )
    db.add(member)
    await db.flush()

    return ProjectMemberResponse(
        user_id=user.id,
        user_name=user.name,
        user_email=user.email,
        user_role=user.role.value,
        notify_email=member.notify_email,
        notify_inapp=member.notify_inapp,
        joined_at=member.joined_at,
    )


@router.delete("/{slug}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    slug: str,
    user_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Remove a member from a project. Admin only."""
    result = await db.execute(
        select(Project).where(Project.slug == slug)
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    member_result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == user_id,
        )
    )
    member = member_result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")

    await db.delete(member)
