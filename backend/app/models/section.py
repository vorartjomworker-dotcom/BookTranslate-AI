import uuid

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Section(Base, TimestampMixin):
    __tablename__ = "sections"
    __table_args__ = (
        UniqueConstraint("chapter_id", "position", name="uq_section_chapter_position"),
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
    parent_section_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sections.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    chapter = relationship("Chapter", back_populates="sections")
    parent = relationship("Section", remote_side="Section.id", back_populates="children")
    children = relationship(
        "Section",
        back_populates="parent",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    blocks = relationship(
        "Block",
        back_populates="section",
        order_by="Block.position",
        passive_deletes=True,
    )
