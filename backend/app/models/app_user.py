import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class AppUser(Base, TimestampMixin):
    __tablename__ = "app_users"
    __table_args__ = (UniqueConstraint("oidc_issuer", "oidc_subject", name="uq_app_user_oidc_identity"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False, default="viewer", index=True)
    api_token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    oidc_issuer: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    oidc_subject: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    assigned_reviews = relationship("HumanReview", back_populates="assigned_user", foreign_keys="HumanReview.assigned_user_id")
    review_comments = relationship("ReviewComment", back_populates="author_user", foreign_keys="ReviewComment.author_user_id")
    audit_events = relationship("AuditEvent", back_populates="actor_user", passive_deletes=True)
