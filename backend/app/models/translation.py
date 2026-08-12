import uuid

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Translation(Base, TimestampMixin):
    __tablename__ = "translations"
    __table_args__ = (
        UniqueConstraint("segment_id", "target_language", name="uq_translation_segment_target"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    segment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("segments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_language: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False, index=True)
    selected_version_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    segment = relationship("Segment", back_populates="translations")
    versions = relationship(
        "TranslationVersion",
        back_populates="translation",
        cascade="all, delete-orphan",
        order_by="TranslationVersion.version_number",
        passive_deletes=True,
    )
    model_runs = relationship(
        "ModelRun",
        back_populates="translation",
        cascade="all, delete-orphan",
        foreign_keys="ModelRun.translation_id",
        passive_deletes=True,
    )
