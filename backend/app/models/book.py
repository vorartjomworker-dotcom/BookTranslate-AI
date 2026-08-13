import uuid

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Book(Base, TimestampMixin):
    __tablename__ = "books"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    source_language: Mapped[str] = mapped_column(String(20), default="en", nullable=False)
    target_language: Mapped[str] = mapped_column(String(20), default="ru", nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(500), nullable=True)
    stored_filename: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_format: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="created", nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    chapters = relationship(
        "Chapter",
        back_populates="book",
        cascade="all, delete-orphan",
        order_by="Chapter.position",
        passive_deletes=True,
    )
    assets = relationship(
        "Asset",
        back_populates="book",
        cascade="all, delete-orphan",
        order_by="Asset.position",
        passive_deletes=True,
    )
    glossary_terms = relationship(
        "GlossaryTerm",
        back_populates="book",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    translation_memory_entries = relationship(
        "TranslationMemoryEntry",
        back_populates="book",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    vision_jobs = relationship(
        "VisionJob",
        back_populates="book",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="VisionJob.created_at",
    )
    figure_renders = relationship(
        "FigureRender",
        back_populates="book",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="FigureRender.created_at",
    )
    figure_render_jobs = relationship(
        "FigureRenderJob",
        back_populates="book",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="FigureRenderJob.created_at",
    )
