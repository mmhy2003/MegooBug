import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr

from app.models.user import UserRole


class InviteCreate(BaseModel):
    email: EmailStr
    role: UserRole = UserRole.DEVELOPER


class InviteResponse(BaseModel):
    id: uuid.UUID
    email: str
    role: UserRole
    token: str
    invited_by: uuid.UUID
    expires_at: datetime
    accepted_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class InviteListResponse(BaseModel):
    invites: list[InviteResponse]
    total: int
