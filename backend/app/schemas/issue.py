from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.issue import IssueStatus, IssueLevel


class IssueResponse(BaseModel):
    """Issue detail response."""
    id: UUID
    project_id: UUID
    issue_number: int | None = None
    title: str
    fingerprint: str
    status: IssueStatus
    level: IssueLevel
    first_seen: datetime
    last_seen: datetime
    event_count: int
    metadata: dict | None = Field(None, alias="metadata_")

    model_config = {"from_attributes": True, "populate_by_name": True}


class IssueUpdate(BaseModel):
    """Request to update an issue's status."""
    status: IssueStatus


class IssueListResponse(BaseModel):
    """Paginated issue list."""
    items: list[IssueResponse]
    total: int
