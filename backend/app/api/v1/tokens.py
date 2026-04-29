from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_developer_or_above
from app.models.api_token import ApiToken
from app.models.user import User
from app.schemas.token import TokenCreate, TokenResponse, TokenCreatedResponse
from app.services.token import generate_api_token

router = APIRouter()


@router.get("", response_model=list[TokenResponse])
async def list_tokens(
    current_user: User = Depends(require_developer_or_above),
    db: AsyncSession = Depends(get_db),
):
    """List all API tokens for the current user."""
    result = await db.execute(
        select(ApiToken)
        .where(ApiToken.user_id == current_user.id)
        .order_by(ApiToken.created_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=TokenCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_token(
    body: TokenCreate,
    current_user: User = Depends(require_developer_or_above),
    db: AsyncSession = Depends(get_db),
):
    """Create a new API token. The raw token is returned only once."""
    raw_token, prefix, token_hash = generate_api_token()

    expires_at = None
    if body.expires_in_days is not None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=body.expires_in_days)

    token = ApiToken(
        user_id=current_user.id,
        name=body.name,
        token_hash=token_hash,
        token_prefix=prefix,
        expires_at=expires_at,
    )
    db.add(token)
    await db.flush()
    await db.refresh(token)

    return TokenCreatedResponse(
        id=token.id,
        name=token.name,
        token_prefix=token.token_prefix,
        scopes=token.scopes,
        last_used_at=token.last_used_at,
        expires_at=token.expires_at,
        created_at=token.created_at,
        raw_token=raw_token,
    )


@router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_token(
    token_id: UUID,
    current_user: User = Depends(require_developer_or_above),
    db: AsyncSession = Depends(get_db),
):
    """Revoke (delete) an API token."""
    result = await db.execute(
        select(ApiToken).where(
            ApiToken.id == token_id,
            ApiToken.user_id == current_user.id,
        )
    )
    token = result.scalar_one_or_none()
    if token is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")

    await db.delete(token)
