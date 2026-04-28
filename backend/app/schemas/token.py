from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TokenCreate(BaseModel):
    """Request to create a new API token."""
    name: str = Field(..., min_length=1, max_length=255, examples=["CI/CD Token"])
    expires_in_days: int | None = Field(
        None, ge=1, le=365,
        description="Days until expiry. Null = never expires.",
    )


class TokenResponse(BaseModel):
    """API token info (without the raw token)."""
    id: UUID
    name: str
    token_prefix: str
    scopes: dict | None = None
    last_used_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenCreatedResponse(TokenResponse):
    """Returned only on creation — includes the raw token (shown once)."""
    raw_token: str = Field(
        ..., description="The full API token. Store this securely — it won't be shown again."
    )
