from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class EventResponse(BaseModel):
    """Event detail response."""
    id: UUID
    issue_id: UUID
    project_id: UUID
    event_id: str
    data: dict
    timestamp: datetime
    received_at: datetime

    model_config = {"from_attributes": True}


class EventListResponse(BaseModel):
    """Paginated event list."""
    items: list[EventResponse]
    total: int
