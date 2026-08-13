import uuid
from decimal import Decimal

from sqlalchemy import Boolean, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ProviderModelPolicy(Base, TimestampMixin):
    __tablename__ = "provider_model_policies"
    __table_args__ = (
        UniqueConstraint("provider", "model", name="uq_provider_model_policy"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False, index=True)
    input_cost_per_million: Mapped[Decimal] = mapped_column(Numeric(14, 6), default=0, nullable=False)
    output_cost_per_million: Mapped[Decimal] = mapped_column(Numeric(14, 6), default=0, nullable=False)
    requests_per_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_per_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_concurrency: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
