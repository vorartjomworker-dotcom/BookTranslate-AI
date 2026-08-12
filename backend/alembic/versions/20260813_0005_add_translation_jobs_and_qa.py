"""add translation jobs and qa

Revision ID: 20260813_0005
Revises: 20260813_0004
Create Date: 2026-08-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260813_0005"
down_revision: Union[str, None] = "20260813_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "translation_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("book_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chapter_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("current_segment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("target_language", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("queue_name", sa.String(length=100), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("total_segments", sa.Integer(), nullable=False),
        sa.Column("completed_segments", sa.Integer(), nullable=False),
        sa.Column("failed_segments", sa.Integer(), nullable=False),
        sa.Column("skipped_segments", sa.Integer(), nullable=False),
        sa.Column("cancellation_requested", sa.Boolean(), nullable=False),
        sa.Column("config_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("errors_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["current_segment_id"], ["segments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_translation_jobs_book_id", "translation_jobs", ["book_id"], unique=False)
    op.create_index("ix_translation_jobs_chapter_id", "translation_jobs", ["chapter_id"], unique=False)
    op.create_index("ix_translation_jobs_current_segment_id", "translation_jobs", ["current_segment_id"], unique=False)
    op.create_index("ix_translation_jobs_status", "translation_jobs", ["status"], unique=False)
    op.create_index("ix_translation_jobs_idempotency_key", "translation_jobs", ["idempotency_key"], unique=True)

    op.create_table(
        "translation_qa_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("translation_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("semantic_accuracy", sa.Float(), nullable=False),
        sa.Column("terminology", sa.Float(), nullable=False),
        sa.Column("completeness", sa.Float(), nullable=False),
        sa.Column("fluency", sa.Float(), nullable=False),
        sa.Column("technical_integrity", sa.Float(), nullable=False),
        sa.Column("style", sa.Float(), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=False),
        sa.Column("verdict", sa.String(length=40), nullable=False),
        sa.Column("issues_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("raw_response", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["translation_version_id"], ["translation_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["model_run_id"], ["model_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_translation_qa_results_translation_version_id", "translation_qa_results", ["translation_version_id"], unique=False)
    op.create_index("ix_translation_qa_results_model_run_id", "translation_qa_results", ["model_run_id"], unique=False)
    op.create_index("ix_translation_qa_results_provider", "translation_qa_results", ["provider"], unique=False)
    op.create_index("ix_translation_qa_results_overall_score", "translation_qa_results", ["overall_score"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_translation_qa_results_overall_score", table_name="translation_qa_results")
    op.drop_index("ix_translation_qa_results_provider", table_name="translation_qa_results")
    op.drop_index("ix_translation_qa_results_model_run_id", table_name="translation_qa_results")
    op.drop_index("ix_translation_qa_results_translation_version_id", table_name="translation_qa_results")
    op.drop_table("translation_qa_results")
    op.drop_index("ix_translation_jobs_idempotency_key", table_name="translation_jobs")
    op.drop_index("ix_translation_jobs_status", table_name="translation_jobs")
    op.drop_index("ix_translation_jobs_current_segment_id", table_name="translation_jobs")
    op.drop_index("ix_translation_jobs_chapter_id", table_name="translation_jobs")
    op.drop_index("ix_translation_jobs_book_id", table_name="translation_jobs")
    op.drop_table("translation_jobs")
