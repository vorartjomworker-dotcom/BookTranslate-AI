"""add figure rendering

Revision ID: 20260813_0009
Revises: 20260813_0008
Create Date: 2026-08-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260813_0009"
down_revision: Union[str, None] = "20260813_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "figure_renders",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("book_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_language", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("stored_filename", sa.String(length=900), nullable=False),
        sa.Column("media_type", sa.String(length=150), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("rendered_regions", sa.Integer(), nullable=False),
        sa.Column("total_regions", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_figure_renders_book_id", "figure_renders", ["book_id"], unique=False)
    op.create_index("ix_figure_renders_asset_id", "figure_renders", ["asset_id"], unique=False)
    op.create_index("ix_figure_renders_target_language", "figure_renders", ["target_language"], unique=False)
    op.create_index("ix_figure_renders_status", "figure_renders", ["status"], unique=False)
    op.create_index("ix_figure_renders_sha256", "figure_renders", ["sha256"], unique=False)

    op.create_table(
        "figure_render_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("book_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_language", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("queue_name", sa.String(length=80), nullable=False),
        sa.Column("total_assets", sa.Integer(), nullable=False),
        sa.Column("completed_assets", sa.Integer(), nullable=False),
        sa.Column("failed_assets", sa.Integer(), nullable=False),
        sa.Column("skipped_assets", sa.Integer(), nullable=False),
        sa.Column("current_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_figure_render_jobs_book_id", "figure_render_jobs", ["book_id"], unique=False)
    op.create_index("ix_figure_render_jobs_asset_id", "figure_render_jobs", ["asset_id"], unique=False)
    op.create_index("ix_figure_render_jobs_status", "figure_render_jobs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_figure_render_jobs_status", table_name="figure_render_jobs")
    op.drop_index("ix_figure_render_jobs_asset_id", table_name="figure_render_jobs")
    op.drop_index("ix_figure_render_jobs_book_id", table_name="figure_render_jobs")
    op.drop_table("figure_render_jobs")

    op.drop_index("ix_figure_renders_sha256", table_name="figure_renders")
    op.drop_index("ix_figure_renders_status", table_name="figure_renders")
    op.drop_index("ix_figure_renders_target_language", table_name="figure_renders")
    op.drop_index("ix_figure_renders_asset_id", table_name="figure_renders")
    op.drop_index("ix_figure_renders_book_id", table_name="figure_renders")
    op.drop_table("figure_renders")
