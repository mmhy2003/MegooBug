import uuid
from datetime import datetime, timezone
import enum

from sqlalchemy import String, Integer, DateTime, ForeignKey, Enum, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class IssueStatus(str, enum.Enum):
    UNRESOLVED = "unresolved"
    RESOLVED = "resolved"
    IGNORED = "ignored"


class IssueLevel(str, enum.Enum):
    FATAL = "fatal"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Issue(Base):
    __tablename__ = "issues"
    __table_args__ = (
        UniqueConstraint("fingerprint", "project_id", name="uq_issues_fingerprint_project"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[IssueStatus] = mapped_column(
        Enum(IssueStatus), nullable=False, default=IssueStatus.UNRESOLVED
    )
    level: Mapped[IssueLevel] = mapped_column(
        Enum(IssueLevel), nullable=False, default=IssueLevel.ERROR
    )
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    event_count: Mapped[int] = mapped_column(Integer, default=1)
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True, default=dict
    )

    # Relationships
    project = relationship("Project", back_populates="issues")
    events = relationship("Event", back_populates="issue", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Issue {self.title[:50]} ({self.status.value})>"
