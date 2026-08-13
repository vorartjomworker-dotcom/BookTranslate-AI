"""add human review book qa and routing policies

Revision ID: 20260813_0006
Revises: 20260813_0005
Create Date: 2026-08-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260813_0006"
down_revision: Union[str, None] = "20260813_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("translation_jobs", sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False))
    op.add_column("translation_jobs", sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False))
    op.add_column("translation_jobs", sa.Column("estimated_cost_usd", sa.Numeric(14, 6), server_default="0", nullable=False))
    op.add_column("model_runs", sa.Column("translation_job_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("model_runs", sa.Column("estimated_cost_usd", sa.Numeric(precision=14, scale=6), nullable=True))
    op.create_foreign_key(
        "fk_model_runs_translation_job_id",
        "model_runs",
        "translation_jobs",
        ["translation_job_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_model_runs_translation_job_id", "model_runs", ["translation_job_id"], unique=False)

    op.create_table(
        "provider_model_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("input_cost_per_million", sa.Numeric(precision=14, scale=6), nullable=False),
        sa.Column("output_cost_per_million", sa.Numeric(precision=14, scale=6), nullable=False),
        sa.Column("requests_per_minute", sa.Integer(), nullable=True),
        sa.Column("tokens_per_minute", sa.Integer(), nullable=True),
        sa.Column("max_concurrency", sa.Integer(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "model", name="uq_provider_model_policy"),
    )
    op.create_index("ix_provider_model_policies_provider", "provider_model_policies", ["provider"], unique=False)
    op.create_index("ix_provider_model_policies_model", "provider_model_policies", ["model"], unique=False)
    op.create_index("ix_provider_model_policies_enabled", "provider_model_policies", ["enabled"], unique=False)
    op.create_index("ix_provider_model_policies_priority", "provider_model_policies", ["priority"], unique=False)

    op.create_table(
        "human_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("translation_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reviewer_id", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("edited_text", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["translation_version_id"], ["translation_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_human_reviews_translation_version_id", "human_reviews", ["translation_version_id"], unique=False)
    op.create_index("ix_human_reviews_reviewer_id", "human_reviews", ["reviewer_id"], unique=False)
    op.create_index("ix_human_reviews_status", "human_reviews", ["status"], unique=False)

    op.create_table(
        "terminology_issues",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("book_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("glossary_term_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("segment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_term", sa.String(length=500), nullable=False),
        sa.Column("expected_target_term", sa.String(length=500), nullable=False),
        sa.Column("translated_text", sa.Text(), nullable=True),
        sa.Column("issue_type", sa.String(length=60), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["glossary_term_id"], ["glossary_terms.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["segment_id"], ["segments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_terminology_issues_book_id", "terminology_issues", ["book_id"], unique=False)
    op.create_index("ix_terminology_issues_glossary_term_id", "terminology_issues", ["glossary_term_id"], unique=False)
    op.create_index("ix_terminology_issues_segment_id", "terminology_issues", ["segment_id"], unique=False)
    op.create_index("ix_terminology_issues_issue_type", "terminology_issues", ["issue_type"], unique=False)
    op.create_index("ix_terminology_issues_severity", "terminology_issues", ["severity"], unique=False)
    op.create_index("ix_terminology_issues_status", "terminology_issues", ["status"], unique=False)

    op.create_table(
        "book_qa_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("book_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_language", sa.String(length=20), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=False),
        sa.Column("translation_coverage", sa.Float(), nullable=False),
        sa.Column("average_segment_quality", sa.Float(), nullable=False),
        sa.Column("terminology_consistency", sa.Float(), nullable=False),
        sa.Column("human_review_coverage", sa.Float(), nullable=False),
        sa.Column("total_segments", sa.Integer(), nullable=False),
        sa.Column("translated_segments", sa.Integer(), nullable=False),
        sa.Column("qa_evaluated_segments", sa.Integer(), nullable=False),
        sa.Column("low_quality_segments", sa.Integer(), nullable=False),
        sa.Column("unresolved_reviews", sa.Integer(), nullable=False),
        sa.Column("terminology_issues", sa.Integer(), nullable=False),
        sa.Column("total_input_tokens", sa.Integer(), nullable=False),
        sa.Column("total_output_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_usd", sa.Numeric(precision=14, scale=6), nullable=False),
        sa.Column("issues_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_book_qa_reports_book_id", "book_qa_reports", ["book_id"], unique=False)
    op.create_index("ix_book_qa_reports_target_language", "book_qa_reports", ["target_language"], unique=False)
    op.create_index("ix_book_qa_reports_overall_score", "book_qa_reports", ["overall_score"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_book_qa_reports_overall_score", table_name="book_qa_reports")
    op.drop_index("ix_book_qa_reports_target_language", table_name="book_qa_reports")
    op.drop_index("ix_book_qa_reports_book_id", table_name="book_qa_reports")
    op.drop_table("book_qa_reports")
    op.drop_index("ix_terminology_issues_status", table_name="terminology_issues")
    op.drop_index("ix_terminology_issues_severity", table_name="terminology_issues")
    op.drop_index("ix_terminology_issues_issue_type", table_name="terminology_issues")
    op.drop_index("ix_terminology_issues_segment_id", table_name="terminology_issues")
    op.drop_index("ix_terminology_issues_glossary_term_id", table_name="terminology_issues")
    op.drop_index("ix_terminology_issues_book_id", table_name="terminology_issues")
    op.drop_table("terminology_issues")
    op.drop_index("ix_human_reviews_status", table_name="human_reviews")
    op.drop_index("ix_human_reviews_reviewer_id", table_name="human_reviews")
    op.drop_index("ix_human_reviews_translation_version_id", table_name="human_reviews")
    op.drop_table("human_reviews")
    op.drop_index("ix_provider_model_policies_priority", table_name="provider_model_policies")
    op.drop_index("ix_provider_model_policies_enabled", table_name="provider_model_policies")
    op.drop_index("ix_provider_model_policies_model", table_name="provider_model_policies")
    op.drop_index("ix_provider_model_policies_provider", table_name="provider_model_policies")
    op.drop_table("provider_model_policies")
    op.drop_index("ix_model_runs_translation_job_id", table_name="model_runs")
    op.drop_constraint("fk_model_runs_translation_job_id", "model_runs", type_="foreignkey")
    op.drop_column("model_runs", "estimated_cost_usd")
    op.drop_column("model_runs", "translation_job_id")
    op.drop_column("translation_jobs", "estimated_cost_usd")
    op.drop_column("translation_jobs", "output_tokens")
    op.drop_column("translation_jobs", "input_tokens")
