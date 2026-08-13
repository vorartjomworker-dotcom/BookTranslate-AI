"""add users review assignments and comments

Revision ID: 20260813_0007
Revises: 20260813_0006
Create Date: 2026-08-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260813_0007"
down_revision: Union[str, None] = "20260813_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("api_token_hash", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("api_token_hash"),
    )
    op.create_index("ix_app_users_email", "app_users", ["email"], unique=False)
    op.create_index("ix_app_users_role", "app_users", ["role"], unique=False)
    op.create_index("ix_app_users_api_token_hash", "app_users", ["api_token_hash"], unique=False)
    op.create_index("ix_app_users_is_active", "app_users", ["is_active"], unique=False)

    op.add_column("human_reviews", sa.Column("assigned_user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("human_reviews", sa.Column("priority", sa.Integer(), server_default="0", nullable=False))
    op.create_foreign_key(
        "fk_human_reviews_assigned_user_id",
        "human_reviews",
        "app_users",
        ["assigned_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_human_reviews_assigned_user_id", "human_reviews", ["assigned_user_id"], unique=False)
    op.create_index("ix_human_reviews_priority", "human_reviews", ["priority"], unique=False)

    op.create_table(
        "review_comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("human_review_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_resolved", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["human_review_id"], ["human_reviews.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_user_id"], ["app_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_review_comments_human_review_id", "review_comments", ["human_review_id"], unique=False)
    op.create_index("ix_review_comments_author_user_id", "review_comments", ["author_user_id"], unique=False)
    op.create_index("ix_review_comments_is_resolved", "review_comments", ["is_resolved"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_review_comments_is_resolved", table_name="review_comments")
    op.drop_index("ix_review_comments_author_user_id", table_name="review_comments")
    op.drop_index("ix_review_comments_human_review_id", table_name="review_comments")
    op.drop_table("review_comments")

    op.drop_index("ix_human_reviews_priority", table_name="human_reviews")
    op.drop_index("ix_human_reviews_assigned_user_id", table_name="human_reviews")
    op.drop_constraint("fk_human_reviews_assigned_user_id", "human_reviews", type_="foreignkey")
    op.drop_column("human_reviews", "priority")
    op.drop_column("human_reviews", "assigned_user_id")

    op.drop_index("ix_app_users_is_active", table_name="app_users")
    op.drop_index("ix_app_users_api_token_hash", table_name="app_users")
    op.drop_index("ix_app_users_role", table_name="app_users")
    op.drop_index("ix_app_users_email", table_name="app_users")
    op.drop_table("app_users")
