import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User, UserRole
from app.models.api_token import ApiToken
from app.services.auth import decode_token
from app.services.token import verify_api_token, is_token_expired
from app.logging import get_logger

logger = get_logger("dependencies")


async def _get_user_from_cookie(
    request: Request,
    db: AsyncSession,
) -> User | None:
    """Try to authenticate via HTTP-only JWT cookie (web UI)."""
    token = request.cookies.get("access_token")
    if not token:
        return None

    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        return None

    user_id = payload.get("sub")
    if user_id is None:
        return None

    result = await db.execute(
        select(User).where(User.id == uuid.UUID(user_id))
    )
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        return None

    return user


async def _get_user_from_bearer(
    request: Request,
    db: AsyncSession,
) -> User | None:
    """Try to authenticate via Bearer API token (/api/0/ compat layer)."""
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return None

    raw_token = auth_header[7:].strip()
    if not raw_token or not raw_token.startswith("mgb_"):
        return None

    # Lookup by prefix for fast candidate narrowing
    prefix = raw_token[:12]
    result = await db.execute(
        select(ApiToken).where(ApiToken.token_prefix == prefix)
    )
    candidates = result.scalars().all()

    for candidate in candidates:
        if verify_api_token(raw_token, candidate.token_hash):
            # Check expiry
            if is_token_expired(candidate.expires_at):
                logger.debug("API token expired: %s", candidate.token_prefix)
                return None

            # Update last_used_at (fire-and-forget, no separate commit needed)
            candidate.last_used_at = datetime.now(timezone.utc)

            # Load the associated user
            user_result = await db.execute(
                select(User).where(User.id == candidate.user_id)
            )
            user = user_result.scalar_one_or_none()
            if user is None or not user.is_active:
                return None

            return user

    return None


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Authenticate user via JWT cookie (primary) or Bearer API token (fallback).

    Web UI uses HTTP-only cookies; external tools (Sentry CLI, MCP) use Bearer tokens.
    """
    # Try cookie auth first (web UI)
    user = await _get_user_from_cookie(request, db)
    if user is not None:
        return user

    # Fallback to Bearer token auth (API compat)
    user = await _get_user_from_bearer(request, db)
    if user is not None:
        return user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
    )


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(*roles: UserRole):
    """Dependency factory that requires the current user to have one of the specified roles."""
    async def role_checker(current_user: CurrentUser) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user
    return role_checker


require_admin = require_role(UserRole.ADMIN)
require_developer_or_above = require_role(UserRole.ADMIN, UserRole.DEVELOPER)
