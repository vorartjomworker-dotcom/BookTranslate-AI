"""add translation quality evaluations

Revision ID: 20260813_0011
Revises: 20260813_0010
Create Date: 2026-08-13
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260813_0011"
down_revision = "20260813_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "translation_quality_evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("translation_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("score_schema", sa.String(length=50), nullable=False),
        sa.Column("evaluation_mode", sa.String(length=40), nullable=False),
        sa.Column("deterministic_score", sa.Float(), nullable=False),
        sa.Column("judge_score", sa.Float(), nullable=True),
        sa.Column("reference_score", sa.Float(), nullable=True),
        sa.Column("final_score", sa.Float(), nullable=False),
        sa.Column("completeness_score", sa.Float(), nullable=False),
        sa.Column("terminology_score", sa.Float(), nullable=False),
        sa.Column("technical_integrity_score", sa.Float(), nullable=False),
        sa.Column("source_leakage_score", sa.Float(), nullable=False),
        sa.Column("hallucination_score", sa.Float(), nullable=False),
        sa.Column("style_score", sa.Float(), nullable=False),
        sa.Column("critical_fail", sa.Boolean(), nullable=False),
        sa.Column("evaluator_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("issues_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("details_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["translation_version_id"], ["translation_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_translation_quality_evaluations_translation_version_id"),
        "translation_quality_evaluations",
        ["translation_version_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_translation_quality_evaluations_score_schema"),
        "translation_quality_evaluations",
        ["score_schema"],
        unique=False,
    )
    op.create_index(
        op.f("ix_translation_quality_evaluations_evaluation_mode"),
        "translation_quality_evaluations",
        ["evaluation_mode"],
        unique=False,
    )
    op.create_index(
        op.f("ix_translation_quality_evaluations_final_score"),
        "translation_quality_evaluations",
        ["final_score"],
        unique=False,
    )
    op.create_index(
        op.f("ix_translation_quality_evaluations_critical_fail"),
        "translation_quality_evaluations",
        ["critical_fail"],
        unique=False,
    )
    op.create_index(
        op.f("ix_translation_quality_evaluations_evaluator_fingerprint"),
        "translation_quality_evaluations",
        ["evaluator_fingerprint"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_translation_quality_evaluations_evaluator_fingerprint"), table_name="translation_quality_evaluations")
    op.drop_index(op.f("ix_translation_quality_evaluations_critical_fail"), table_name="translation_quality_evaluations")
    op.drop_index(op.f("ix_translation_quality_evaluations_final_score"), table_name="translation_quality_evaluations")
    op.drop_index(op.f("ix_translation_quality_evaluations_evaluation_mode"), table_name="translation_quality_evaluations")
    op.drop_index(op.f("ix_translation_quality_evaluations_score_schema"), table_name="translation_quality_evaluations")
    op.drop_index(op.f("ix_translation_quality_evaluations_translation_version_id"), table_name="translation_quality_evaluations")
    op.drop_table("translation_quality_evaluations")
