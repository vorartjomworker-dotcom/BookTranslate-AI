import uuid
from decimal import Decimal

from sqlalchemy import Float, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class BookQAReport(Base, TimestampMixin):
    __tablename__ = "book_qa_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    book_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_language: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    translation_coverage: Mapped[float] = mapped_column(Float, nullable=False)
    average_segment_quality: Mapped[float] = mapped_column(Float, nullable=False)
    terminology_consistency: Mapped[float] = mapped_column(Float, nullable=False)
    human_review_coverage: Mapped[float] = mapped_column(Float, nullable=False)
    total_segments: Mapped[int] = mapped_column(Integer, nullable=False)
    translated_segments: Mapped[int] = mapped_column(Integer, nullable=False)
    qa_evaluated_segments: Mapped[int] = mapped_column(Integer, nullable=False)
    low_quality_segments: Mapped[int] = mapped_column(Integer, nullable=False)
    unresolved_reviews: Mapped[int] = mapped_column(Integer, nullable=False)
    terminology_issues: Mapped[int] = mapped_column(Integer, nullable=False)
    total_input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost_usd: Mapped[Decimal] = mapped_column(Numeric(14, 6), default=0, nullable=False)
    issues_json: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    book = relationship("Book")
