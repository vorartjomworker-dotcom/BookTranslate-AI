import uuid

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class TranslationQAResult(Base, TimestampMixin):
    __tablename__ = "translation_qa_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    translation_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("translation_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    model_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    semantic_accuracy: Mapped[float] = mapped_column(Float, nullable=False)
    terminology: Mapped[float] = mapped_column(Float, nullable=False)
    completeness: Mapped[float] = mapped_column(Float, nullable=False)
    fluency: Mapped[float] = mapped_column(Float, nullable=False)
    technical_integrity: Mapped[float] = mapped_column(Float, nullable=False)
    style: Mapped[float] = mapped_column(Float, nullable=False)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    verdict: Mapped[str] = mapped_column(String(40), nullable=False)
    issues_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
