import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class TerminologyIssue(Base, TimestampMixin):
    __tablename__ = "terminology_issues"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    book_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    glossary_term_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("glossary_terms.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    segment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("segments.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    source_term: Mapped[str] = mapped_column(String(500), nullable=False)
    expected_target_term: Mapped[str] = mapped_column(String(500), nullable=False)
    translated_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    issue_type: Mapped[str] = mapped_column(String(60), default="missing_required_term", nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), default="warning", nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), default="open", nullable=False, index=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    book = relationship("Book")
    glossary_term = relationship("GlossaryTerm")
    segment = relationship("Segment")
