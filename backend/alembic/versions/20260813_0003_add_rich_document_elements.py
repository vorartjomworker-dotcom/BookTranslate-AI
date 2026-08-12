"""add rich document elements

Revision ID: 20260813_0003
Revises: 20260813_0002
Create Date: 2026-08-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260813_0003"
down_revision: Union[str, None] = "20260813_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("book_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("asset_type", sa.String(length=50), nullable=False),
        sa.Column("original_filename", sa.String(length=500), nullable=True),
        sa.Column("stored_filename", sa.String(length=700), nullable=False),
        sa.Column("media_type", sa.String(length=150), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("book_id", "position", name="uq_asset_book_position"),
    )
    op.create_index("ix_assets_book_id", "assets", ["book_id"], unique=False)
    op.create_index("ix_assets_sha256", "assets", ["sha256"], unique=False)

    op.create_table(
        "figures",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("block_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alt_text", sa.String(length=1000), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["block_id"], ["blocks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("block_id"),
    )
    op.create_index("ix_figures_asset_id", "figures", ["asset_id"], unique=False)
    op.create_index("ix_figures_block_id", "figures", ["block_id"], unique=True)

    op.create_table(
        "document_tables",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("block_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rows_count", sa.Integer(), nullable=False),
        sa.Column("columns_count", sa.Integer(), nullable=False),
        sa.Column("data_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["block_id"], ["blocks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("block_id"),
    )
    op.create_index("ix_document_tables_block_id", "document_tables", ["block_id"], unique=True)

    op.create_table(
        "captions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("block_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_block_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("label", sa.String(length=100), nullable=True),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["block_id"], ["blocks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_block_id"], ["blocks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("block_id"),
    )
    op.create_index("ix_captions_block_id", "captions", ["block_id"], unique=True)
    op.create_index("ix_captions_target_block_id", "captions", ["target_block_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_captions_target_block_id", table_name="captions")
    op.drop_index("ix_captions_block_id", table_name="captions")
    op.drop_table("captions")
    op.drop_index("ix_document_tables_block_id", table_name="document_tables")
    op.drop_table("document_tables")
    op.drop_index("ix_figures_block_id", table_name="figures")
    op.drop_index("ix_figures_asset_id", table_name="figures")
    op.drop_table("figures")
    op.drop_index("ix_assets_sha256", table_name="assets")
    op.drop_index("ix_assets_book_id", table_name="assets")
    op.drop_table("assets")
