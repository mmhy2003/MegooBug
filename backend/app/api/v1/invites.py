import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import require_admin
from app.models.invite import Invite
from app.models.user import User
from app.schemas.invite import InviteCreate, InviteListResponse, InviteResponse
from app.services.auth import create_invite_token

router = APIRouter()


@router.post("", response_model=InviteResponse, status_code=status.HTTP_201_CREATED)
async def create_invite(
    data: InviteCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create an invite link for a new user (admin only).
    If a pending invite already exists for this email, it is replaced."""
    # Check if email is already registered
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email is already registered",
        )

    # Delete any existing pending invites for this email (allows re-invite)
    result = await db.execute(
        select(Invite).where(
            Invite.email == data.email,
            Invite.accepted_at.is_(None),
        )
    )
    existing = result.scalars().all()
    for old_invite in existing:
        await db.delete(old_invite)

    invite = Invite(
        email=data.email,
        role=data.role,
        token=create_invite_token(),
        invited_by=current_user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(
            hours=settings.INVITE_TOKEN_EXPIRE_HOURS
        ),
    )
    db.add(invite)
    await db.flush()
    await db.refresh(invite)

    return invite


@router.get("", response_model=InviteListResponse)
async def list_invites(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all pending invites (admin only)."""
    result = await db.execute(
        select(Invite)
        .where(Invite.accepted_at.is_(None))
        .order_by(Invite.created_at.desc())
    )
    invites = result.scalars().all()

    count_result = await db.execute(
        select(func.count(Invite.id)).where(Invite.accepted_at.is_(None))
    )
    total = count_result.scalar()

    return {"invites": invites, "total": total}


@router.delete("/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invite(
    invite_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a pending invite (admin only)."""
    result = await db.execute(select(Invite).where(Invite.id == invite_id))
    invite = result.scalar_one_or_none()

    if invite is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invite not found",
        )

    if invite.accepted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invite has already been accepted",
        )

    await db.delete(invite)
    await db.flush()
