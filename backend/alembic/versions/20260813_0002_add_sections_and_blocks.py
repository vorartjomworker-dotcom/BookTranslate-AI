"""add sections and blocks

Revision ID: 20260813_0002
Revises: 20260813_0001
Create Date: 2026-08-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260813_0002"
down_revision: Union[str, None] = "20260813_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chapter_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_section_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=1000), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_section_id"], ["sections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chapter_id", "position", name="uq_section_chapter_position"),
    )
    op.create_index("ix_sections_chapter_id", "sections", ["chapter_id"], unique=False)
    op.create_index("ix_sections_parent_section_id", "sections", ["parent_section_id"], unique=False)

    op.create_table(
        "blocks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chapter_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("section_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("block_type", sa.String(length=50), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["section_id"], ["sections.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chapter_id", "position", name="uq_block_chapter_position"),
    )
    op.create_index("ix_blocks_chapter_id", "blocks", ["chapter_id"], unique=False)
    op.create_index("ix_blocks_section_id", "blocks", ["section_id"], unique=False)

    op.add_column("segments", sa.Column("block_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_segments_block_id_blocks",
        "segments",
        "blocks",
        ["block_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_segments_block_id", "segments", ["block_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_segments_block_id", table_name="segments")
    op.drop_constraint("fk_segments_block_id_blocks", "segments", type_="foreignkey")
    op.drop_column("segments", "block_id")

    op.drop_index("ix_blocks_section_id", table_name="blocks")
    op.drop_index("ix_blocks_chapter_id", table_name="blocks")
    op.drop_table("blocks")

    op.drop_index("ix_sections_parent_section_id", table_name="sections")
    op.drop_index("ix_sections_chapter_id", table_name="sections")
    op.drop_table("sections")
