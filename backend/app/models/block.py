import uuid

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Block(Base, TimestampMixin):
    __tablename__ = "blocks"
    __table_args__ = (
        UniqueConstraint("chapter_id", "position", name="uq_block_chapter_position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    chapter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chapters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    section_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sections.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    block_type: Mapped[str] = mapped_column(String(50), nullable=False, default="paragraph")
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    chapter = relationship("Chapter", back_populates="blocks")
    section = relationship("Section", back_populates="blocks")
    segments = relationship("Segment", back_populates="block", order_by="Segment.position")
    figure = relationship("Figure", back_populates="block", uselist=False, cascade="all, delete-orphan")
    table_data = relationship(
        "DocumentTable",
        back_populates="block",
        uselist=False,
        cascade="all, delete-orphan",
    )
    caption = relationship(
        "Caption",
        foreign_keys="Caption.block_id",
        back_populates="block",
        uselist=False,
        cascade="all, delete-orphan",
    )
