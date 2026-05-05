from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TeamCreate(BaseModel):
    """Request to create a new team."""
    name: str = Field(..., min_length=1, max_length=255, examples=["Backend Team"])


class TeamUpdate(BaseModel):
    """Request to update a team."""
    name: str | None = Field(None, min_length=1, max_length=255)


class TeamResponse(BaseModel):
    """Team detail response."""
    id: UUID
    team_number: int
    name: str
    slug: str
    created_at: datetime
    member_count: int = 0
    project_count: int = 0

    model_config = {"from_attributes": True}


class TeamMemberResponse(BaseModel):
    """Team member info."""
    user_id: UUID
    user_name: str
    user_email: str
    user_role: str
    team_role: str
    joined_at: datetime


class TeamMemberAdd(BaseModel):
    """Request to add a member to a team."""
    user_id: UUID
    role: str = "member"  # "admin" or "member"
