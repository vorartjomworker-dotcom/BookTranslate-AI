import uuid

from sqlalchemy import Boolean, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class TranslationQualityEvaluation(Base, TimestampMixin):
    __tablename__ = "translation_quality_evaluations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    translation_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("translation_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    score_schema: Mapped[str] = mapped_column(String(50), default="quality-v2", nullable=False, index=True)
    evaluation_mode: Mapped[str] = mapped_column(String(40), default="runtime", nullable=False, index=True)
    deterministic_score: Mapped[float] = mapped_column(Float, nullable=False)
    judge_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    reference_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    final_score: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    completeness_score: Mapped[float] = mapped_column(Float, nullable=False)
    terminology_score: Mapped[float] = mapped_column(Float, nullable=False)
    technical_integrity_score: Mapped[float] = mapped_column(Float, nullable=False)
    source_leakage_score: Mapped[float] = mapped_column(Float, nullable=False)
    hallucination_score: Mapped[float] = mapped_column(Float, nullable=False)
    style_score: Mapped[float] = mapped_column(Float, nullable=False)
    critical_fail: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    evaluator_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    issues_json: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    details_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
