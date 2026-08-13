import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class FigureRender(Base, TimestampMixin):
    __tablename__ = "figure_renders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    book_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_language: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    render_mode: Mapped[str] = mapped_column(String(40), nullable=False, default="overlay", index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="completed", index=True)
    stored_filename: Mapped[str] = mapped_column(String(900), nullable=False)
    media_type: Mapped[str] = mapped_column(String(150), nullable=False, default="image/png")
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    rendered_regions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_regions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    book = relationship("Book", back_populates="figure_renders")
    asset = relationship("Asset", back_populates="figure_renders")
