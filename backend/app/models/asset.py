import uuid

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Asset(Base, TimestampMixin):
    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("book_id", "position", name="uq_asset_book_position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    book_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    asset_type: Mapped[str] = mapped_column(String(50), nullable=False, default="image")
    original_filename: Mapped[str | None] = mapped_column(String(500), nullable=True)
    stored_filename: Mapped[str] = mapped_column(String(700), nullable=False)
    media_type: Mapped[str | None] = mapped_column(String(150), nullable=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    book = relationship("Book", back_populates="assets")
    figures = relationship("Figure", back_populates="asset", passive_deletes=True)
    vision_extractions = relationship(
        "VisionExtraction",
        back_populates="asset",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="VisionExtraction.created_at",
    )
