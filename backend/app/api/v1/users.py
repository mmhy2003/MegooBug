import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import CurrentUser, require_admin
from app.models.user import User, UserRole
from app.schemas.user import (
    PasswordUpdate,
    RoleUpdate,
    UserListResponse,
    UserResponse,
    UserUpdate,
)
from app.services.auth import hash_password, verify_password

router = APIRouter()


@router.get("", response_model=UserListResponse)
async def list_users(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 50,
):
    """List all users (admin only)."""
    result = await db.execute(
        select(User).order_by(User.created_at.desc()).offset(skip).limit(limit)
    )
    users = result.scalars().all()

    count_result = await db.execute(select(func.count(User.id)))
    total = count_result.scalar()

    return {"users": users, "total": total}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: CurrentUser):
    """Get current user profile."""
    return current_user


@router.patch("/me", response_model=UserResponse)
async def update_me(
    data: UserUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Update current user profile."""
    if data.name is not None:
        current_user.name = data.name
    if data.email is not None:
        # Check uniqueness
        result = await db.execute(
            select(User).where(User.email == data.email, User.id != current_user.id)
        )
        if result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already in use",
            )
        current_user.email = data.email
    if data.avatar_url is not None:
        current_user.avatar_url = data.avatar_url

    await db.flush()
    await db.refresh(current_user)
    return current_user


@router.patch("/me/password", response_model=dict)
async def update_password(
    data: PasswordUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Change current user's password."""
    if not verify_password(data.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    current_user.password_hash = hash_password(data.new_password)
    await db.flush()
    return {"message": "Password updated"}


# ── Notification Preferences ──

_VALID_PREF_KEYS = {"new_issue", "regression", "assigned"}
_VALID_CHANNELS = {"inapp", "email"}
_DEFAULT_PREF = {"inapp": True, "email": True}


@router.get("/me/notification-preferences")
async def get_notification_preferences(
    current_user: CurrentUser,
):
    """Get current user's notification preferences."""
    prefs = current_user.notification_preferences or {}
    # Ensure all keys have defaults
    result = {}
    for key in _VALID_PREF_KEYS:
        result[key] = {**_DEFAULT_PREF, **prefs.get(key, {})}
    return {"preferences": result}


@router.put("/me/notification-preferences")
async def update_notification_preferences(
    body: dict,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Update current user's notification preferences.

    Body: {"preferences": {"new_issue": {"inapp": true, "email": false}, ...}}
    """
    import json
    from sqlalchemy.orm.attributes import flag_modified

    incoming = body.get("preferences", {})
    if not isinstance(incoming, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="preferences must be an object",
        )

    # Deep-copy so SQLAlchemy detects the mutation (shallow copy shares nested dicts)
    current_prefs = json.loads(json.dumps(current_user.notification_preferences or {}))

    for key in _VALID_PREF_KEYS:
        if key in incoming and isinstance(incoming[key], dict):
            entry = current_prefs.get(key, dict(_DEFAULT_PREF))
            for ch in _VALID_CHANNELS:
                if ch in incoming[key] and isinstance(incoming[key][ch], bool):
                    entry[ch] = incoming[key][ch]
            current_prefs[key] = entry

    current_user.notification_preferences = current_prefs
    flag_modified(current_user, "notification_preferences")
    await db.flush()
    await db.refresh(current_user)

    return {"preferences": current_prefs}


@router.patch("/{user_id}/role", response_model=UserResponse)
async def change_user_role(
    user_id: uuid.UUID,
    data: RoleUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Change a user's role (admin only)."""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change your own role",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user.role = data.role
    await db.flush()
    await db.refresh(user)
    return user


@router.patch("/{user_id}/status", response_model=UserResponse)
async def toggle_user_status(
    user_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Enable/disable a user (admin only)."""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot disable yourself",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user.is_active = not user.is_active
    await db.flush()
    await db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Remove a user (admin only)."""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete yourself",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    await db.delete(user)
    await db.flush()
