from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    """Request to create a new project."""
    name: str = Field(..., min_length=1, max_length=255, examples=["Web Frontend"])
    platform: str | None = Field(None, max_length=100, examples=["javascript", "python", "go"])


class ProjectUpdate(BaseModel):
    """Request to update a project."""
    name: str | None = Field(None, min_length=1, max_length=255)
    platform: str | None = Field(None, max_length=100)


class ProjectResponse(BaseModel):
    """Project detail response."""
    id: UUID
    project_number: int
    name: str
    slug: str
    platform: str | None = None
    dsn_public_key: str
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectWithDSN(ProjectResponse):
    """Project response with full DSN URL."""
    dsn: str = ""


class ProjectMemberResponse(BaseModel):
    """Project member info."""
    user_id: UUID
    user_name: str
    user_email: str
    user_role: str
    notify_email: bool
    notify_inapp: bool
    joined_at: datetime


class ProjectMemberAdd(BaseModel):
    """Request to add a member to a project."""
    user_id: UUID
    notify_email: bool = True
    notify_inapp: bool = True
