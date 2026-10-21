import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import CurrentUser
from app.models.user import User, UserRole
from app.models.invite import Invite
from app.schemas.auth import (
    InviteAcceptRequest,
    LoginRequest,
    MessageResponse,
    MfaChallengeResponse,
    SignupRequest,
)
from app.schemas.user import UserResponse
from app.services.auth import (
    decode_token,
    hash_password,
    issue_auth_cookies,
    issue_mfa_pending_cookie,
    token_version_matches,
    verify_password,
)

router = APIRouter()


@router.post("/login", response_model=UserResponse | MfaChallengeResponse)
async def login(
    data: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Check the password; then either sign in, or start the second step.

    A user with 2FA (or one an admin requires to have it) gets only a
    short-lived pending cookie here; session cookies come after /auth/2fa/*.
    """
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    if user.mfa_enrolled or user.mfa_required:
        issue_mfa_pending_cookie(response, user)
        return MfaChallengeResponse(
            mfa_required="verify" if user.mfa_enrolled else "setup",
            methods=user.mfa_methods,
            email=user.email,
        )

    issue_auth_cookies(response, user)

    return user


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    data: SignupRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Register a new user (if signup is enabled)."""
    if not settings.ALLOW_SIGNUP:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Signup is disabled",
        )

    # Check if email already exists
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Determine role: first user becomes admin
    user_count_result = await db.execute(select(User))
    is_first_user = user_count_result.scalars().first() is None

    user = User(
        email=data.email,
        name=data.name,
        password_hash=hash_password(data.password),
        role=UserRole.ADMIN if is_first_user else UserRole.VIEWER,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    issue_auth_cookies(response, user)

    return user


@router.post("/refresh", response_model=MessageResponse)
async def refresh_access_token(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Refresh access token using refresh token cookie."""
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token",
        )

    payload = decode_token(token)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    user_id = payload.get("sub")
    result = await db.execute(
        select(User).where(User.id == uuid.UUID(user_id))
    )
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    # Reject refresh tokens issued before the last password change
    if not token_version_matches(payload, user):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    # Rotate tokens
    issue_auth_cookies(response, user)

    return {"message": "Token refreshed"}


@router.post("/logout", response_model=MessageResponse)
async def logout(response: Response, current_user: CurrentUser):
    """Clear auth cookies to log out."""
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"message": "Logged out"}


@router.post("/accept-invite", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def accept_invite(
    data: InviteAcceptRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Register via an invite token."""
    result = await db.execute(
        select(Invite).where(
            Invite.token == data.token,
            Invite.accepted_at.is_(None),
        )
    )
    invite = result.scalar_one_or_none()

    if invite is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or already used invite",
        )

    if invite.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Invite has expired",
        )

    # Check if email already registered
    result = await db.execute(select(User).where(User.email == invite.email))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        email=invite.email,
        name=data.name,
        password_hash=hash_password(data.password),
        role=invite.role,
    )
    db.add(user)

    invite.accepted_at = datetime.now(timezone.utc)

    await db.flush()
    await db.refresh(user)

    issue_auth_cookies(response, user)

    return user
