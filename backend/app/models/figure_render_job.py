import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class FigureRenderJob(Base, TimestampMixin):
    __tablename__ = "figure_render_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    book_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=True, index=True
    )
    target_language: Mapped[str] = mapped_column(String(20), nullable=False)
    render_mode: Mapped[str] = mapped_column(String(40), nullable=False, default="overlay", index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="queued", index=True)
    queue_name: Mapped[str] = mapped_column(String(80), nullable=False, default="figure-render")
    total_assets: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_assets: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_assets: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_assets: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    book = relationship("Book", back_populates="figure_render_jobs")
    asset = relationship("Asset", foreign_keys=[asset_id])
