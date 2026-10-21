import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.user import UserRole


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    role: UserRole
    is_active: bool
    avatar_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    mfa_required: bool = False
    mfa_methods: list[str] = []

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    avatar_url: Optional[str] = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("Name cannot be empty")
        return v


class PasswordUpdate(BaseModel):
    # No length floor: a short wrong password should get "incorrect", not a 422
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)


class RoleUpdate(BaseModel):
    role: UserRole


class UserListResponse(BaseModel):
    users: list[UserResponse]
    total: int


# ── Two-factor authentication ──


class PasswordConfirm(BaseModel):
    password: str = Field(..., min_length=1, max_length=128)


class PasskeyInfo(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime
    last_used_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TwoFactorStatus(BaseModel):
    enabled: bool
    required: bool
    methods: list[str]
    totp_enabled_at: Optional[datetime] = None
    passkeys: list[PasskeyInfo]


class PasskeyRename(BaseModel):
    name: str = Field(..., max_length=100)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name cannot be empty")
        return v
