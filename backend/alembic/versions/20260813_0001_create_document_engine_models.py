"""create document engine models

Revision ID: 20260813_0001
Revises:
Create Date: 2026-08-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260813_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "books",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("source_language", sa.String(length=20), nullable=False),
        sa.Column("target_language", sa.String(length=20), nullable=False),
        sa.Column("original_filename", sa.String(length=500), nullable=True),
        sa.Column("stored_filename", sa.String(length=500), nullable=True),
        sa.Column("file_format", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_books_status", "books", ["status"], unique=False)

    op.create_table(
        "chapters",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("book_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("source_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("book_id", "position", name="uq_chapter_book_position"),
    )
    op.create_index("ix_chapters_book_id", "chapters", ["book_id"], unique=False)

    op.create_table(
        "segments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chapter_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("segment_type", sa.String(length=50), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("translated_text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chapter_id", "position", name="uq_segment_chapter_position"),
    )
    op.create_index("ix_segments_chapter_id", "segments", ["chapter_id"], unique=False)
    op.create_index("ix_segments_source_hash", "segments", ["source_hash"], unique=False)
    op.create_index("ix_segments_status", "segments", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_segments_status", table_name="segments")
    op.drop_index("ix_segments_source_hash", table_name="segments")
    op.drop_index("ix_segments_chapter_id", table_name="segments")
    op.drop_table("segments")

    op.drop_index("ix_chapters_book_id", table_name="chapters")
    op.drop_table("chapters")

    op.drop_index("ix_books_status", table_name="books")
    op.drop_table("books")
