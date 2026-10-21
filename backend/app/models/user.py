import uuid
from datetime import datetime, timezone
import enum

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    DEVELOPER = "developer"
    VIEWER = "viewer"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole), nullable=False, default=UserRole.VIEWER
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Bumped on password change; JWTs carrying an older "tv" claim are rejected.
    token_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # ── Two-factor authentication ──
    # Admin-set: the user must have at least one 2FA method to sign in.
    mfa_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # TOTP secrets are Fernet-encrypted (app.services.mfa); the pending one
    # only becomes active once a code from it is confirmed.
    totp_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    totp_pending_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    totp_enabled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Last accepted TOTP time step, for replay protection
    totp_last_step: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # Outstanding WebAuthn challenge (base64url), registration or authentication
    webauthn_challenge: Mapped[str | None] = mapped_column(Text, nullable=True)
    webauthn_challenge_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # The one valid "password ok, second step pending" credential and its failures
    mfa_pending_jti: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mfa_pending_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # Consecutive second-step failures across logins, and the backoff they earned
    mfa_failed_streak: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    mfa_retry_after: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    notification_preferences: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=lambda: {
            "new_issue": {"inapp": True, "email": True},
            "regression": {"inapp": True, "email": True},
            "assigned": {"inapp": True, "email": True},
        },
        server_default='{"new_issue":{"inapp":true,"email":true},"regression":{"inapp":true,"email":true},"assigned":{"inapp":true,"email":true}}',
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    projects_created = relationship("Project", back_populates="creator")
    project_memberships = relationship("ProjectMember", back_populates="user")
    team_memberships = relationship("TeamMember", back_populates="user")
    notifications = relationship("Notification", back_populates="user")
    invites_sent = relationship("Invite", back_populates="invited_by_user")
    api_tokens = relationship("ApiToken", back_populates="user", cascade="all, delete-orphan")
    # selectin: loaded with every user query, so mfa_methods works in async code
    webauthn_credentials = relationship(
        "WebAuthnCredential",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="WebAuthnCredential.created_at",
    )

    def __init__(self, **kwargs):
        # Start new users with a loaded, empty collection: reading an unloaded
        # one on a just-flushed object would need lazy IO, which async forbids.
        kwargs.setdefault("webauthn_credentials", [])
        super().__init__(**kwargs)

    @property
    def mfa_methods(self) -> list[str]:
        """Enrolled second factors, passkey first."""
        methods = []
        if self.webauthn_credentials:
            methods.append("passkey")
        if self.totp_enabled_at is not None:
            methods.append("totp")
        return methods

    @property
    def mfa_enrolled(self) -> bool:
        return bool(self.mfa_methods)

    def __repr__(self) -> str:
        return f"<User {self.email} ({self.role.value})>"
