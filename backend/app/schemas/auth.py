from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)


class SignupRequest(BaseModel):
    email: EmailStr
    name: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)


class InviteAcceptRequest(BaseModel):
    token: str
    name: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MessageResponse(BaseModel):
    message: str


class MfaChallengeResponse(BaseModel):
    """Login accepted the password; a second step (or forced setup) is next."""
    mfa_required: Literal["verify", "setup"]
    methods: list[str]
    email: str


class TotpCodeRequest(BaseModel):
    code: str = Field(..., max_length=20)


class PasskeyAssertionRequest(BaseModel):
    credential: dict


class TotpSetupResponse(BaseModel):
    secret: str
    otpauth_uri: str


class PasskeyRegistrationRequest(BaseModel):
    credential: dict
    name: str = Field("", max_length=100)
