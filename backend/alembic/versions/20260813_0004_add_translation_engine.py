"""add translation engine

Revision ID: 20260813_0004
Revises: 20260813_0003
Create Date: 2026-08-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260813_0004"
down_revision: Union[str, None] = "20260813_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def upgrade() -> None:
    created_at, updated_at = _timestamps()
    op.create_table(
        "prompt_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        created_at,
        updated_at,
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "version_number", name="uq_prompt_name_version"),
    )
    op.create_index("ix_prompt_versions_name", "prompt_versions", ["name"], unique=False)
    op.create_index("ix_prompt_versions_role", "prompt_versions", ["role"], unique=False)
    op.create_index("ix_prompt_versions_is_active", "prompt_versions", ["is_active"], unique=False)

    created_at, updated_at = _timestamps()
    op.create_table(
        "translations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("segment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_language", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("selected_version_number", sa.Integer(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        created_at,
        updated_at,
        sa.ForeignKeyConstraint(["segment_id"], ["segments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("segment_id", "target_language", name="uq_translation_segment_target"),
    )
    op.create_index("ix_translations_segment_id", "translations", ["segment_id"], unique=False)
    op.create_index("ix_translations_status", "translations", ["status"], unique=False)

    created_at, updated_at = _timestamps()
    op.create_table(
        "model_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("segment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("translation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("prompt_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("provider_request_id", sa.String(length=250), nullable=True),
        sa.Column("request_hash", sa.String(length=64), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("output_text", sa.Text(), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        created_at,
        updated_at,
        sa.ForeignKeyConstraint(["prompt_version_id"], ["prompt_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["segment_id"], ["segments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["translation_id"], ["translations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("segment_id", "translation_id", "prompt_version_id", "provider", "role", "status", "request_hash"):
        op.create_index(f"ix_model_runs_{column}", "model_runs", [column], unique=False)

    created_at, updated_at = _timestamps()
    op.create_table(
        "translation_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("translation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=True),
        sa.Column("model", sa.String(length=200), nullable=True),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("is_final", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        created_at,
        updated_at,
        sa.ForeignKeyConstraint(["model_run_id"], ["model_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["translation_id"], ["translations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("translation_id", "version_number", name="uq_translation_version_number"),
    )
    op.create_index("ix_translation_versions_translation_id", "translation_versions", ["translation_id"], unique=False)
    op.create_index("ix_translation_versions_model_run_id", "translation_versions", ["model_run_id"], unique=False)
    op.create_index("ix_translation_versions_is_final", "translation_versions", ["is_final"], unique=False)

    created_at, updated_at = _timestamps()
    op.create_table(
        "glossary_terms",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("book_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_term", sa.String(length=500), nullable=False),
        sa.Column("target_term", sa.String(length=500), nullable=False),
        sa.Column("source_language", sa.String(length=20), nullable=False),
        sa.Column("target_language", sa.String(length=20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("case_sensitive", sa.Boolean(), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        created_at,
        updated_at,
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("book_id", "source_term", "target_language", name="uq_glossary_book_term_target"),
    )
    op.create_index("ix_glossary_terms_book_id", "glossary_terms", ["book_id"], unique=False)
    op.create_index("ix_glossary_terms_target_language", "glossary_terms", ["target_language"], unique=False)
    op.create_index("ix_glossary_terms_approved", "glossary_terms", ["approved"], unique=False)
    op.create_index("ix_glossary_terms_status", "glossary_terms", ["status"], unique=False)

    created_at, updated_at = _timestamps()
    op.create_table(
        "translation_memory_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("book_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("origin_translation_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("target_text", sa.Text(), nullable=False),
        sa.Column("source_language", sa.String(length=20), nullable=False),
        sa.Column("target_language", sa.String(length=20), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("usage_count", sa.Integer(), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        created_at,
        updated_at,
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["origin_translation_version_id"],
            ["translation_versions.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("book_id", "source_hash", "target_language", name="uq_tm_book_hash_target"),
    )
    op.create_index("ix_translation_memory_entries_book_id", "translation_memory_entries", ["book_id"], unique=False)
    op.create_index("ix_translation_memory_entries_origin_translation_version_id", "translation_memory_entries", ["origin_translation_version_id"], unique=False)
    op.create_index("ix_translation_memory_entries_source_hash", "translation_memory_entries", ["source_hash"], unique=False)
    op.create_index("ix_translation_memory_entries_target_language", "translation_memory_entries", ["target_language"], unique=False)
    op.create_index("ix_translation_memory_entries_approved", "translation_memory_entries", ["approved"], unique=False)


def downgrade() -> None:
    op.drop_table("translation_memory_entries")
    op.drop_table("glossary_terms")
    op.drop_table("translation_versions")
    op.drop_table("model_runs")
    op.drop_table("translations")
    op.drop_table("prompt_versions")
