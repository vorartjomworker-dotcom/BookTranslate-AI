"""add sessions SCIM fields and render modes

Revision ID: 20260813_0010
Revises: 20260813_0009
Create Date: 2026-08-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260813_0010"
down_revision: Union[str, None] = "20260813_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("app_users", sa.Column("scim_external_id", sa.String(length=500), nullable=True))
    op.add_column("app_users", sa.Column("scim_managed", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.create_index("ix_app_users_scim_external_id", "app_users", ["scim_external_id"], unique=True)
    op.create_index("ix_app_users_scim_managed", "app_users", ["scim_managed"], unique=False)

    op.create_table(
        "user_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("access_token_hash", sa.String(length=64), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refresh_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["app_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("access_token_hash"),
        sa.UniqueConstraint("refresh_token_hash"),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"], unique=False)
    op.create_index("ix_user_sessions_access_token_hash", "user_sessions", ["access_token_hash"], unique=True)
    op.create_index("ix_user_sessions_refresh_token_hash", "user_sessions", ["refresh_token_hash"], unique=True)
    op.create_index("ix_user_sessions_expires_at", "user_sessions", ["expires_at"], unique=False)
    op.create_index("ix_user_sessions_refresh_expires_at", "user_sessions", ["refresh_expires_at"], unique=False)
    op.create_index("ix_user_sessions_revoked_at", "user_sessions", ["revoked_at"], unique=False)

    op.add_column(
        "figure_renders",
        sa.Column("render_mode", sa.String(length=40), server_default="overlay", nullable=False),
    )
    op.create_index("ix_figure_renders_render_mode", "figure_renders", ["render_mode"], unique=False)
    op.add_column(
        "figure_render_jobs",
        sa.Column("render_mode", sa.String(length=40), server_default="overlay", nullable=False),
    )
    op.create_index("ix_figure_render_jobs_render_mode", "figure_render_jobs", ["render_mode"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_figure_render_jobs_render_mode", table_name="figure_render_jobs")
    op.drop_column("figure_render_jobs", "render_mode")
    op.drop_index("ix_figure_renders_render_mode", table_name="figure_renders")
    op.drop_column("figure_renders", "render_mode")

    op.drop_index("ix_user_sessions_revoked_at", table_name="user_sessions")
    op.drop_index("ix_user_sessions_refresh_expires_at", table_name="user_sessions")
    op.drop_index("ix_user_sessions_expires_at", table_name="user_sessions")
    op.drop_index("ix_user_sessions_refresh_token_hash", table_name="user_sessions")
    op.drop_index("ix_user_sessions_access_token_hash", table_name="user_sessions")
    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_table("user_sessions")

    op.drop_index("ix_app_users_scim_managed", table_name="app_users")
    op.drop_index("ix_app_users_scim_external_id", table_name="app_users")
    op.drop_column("app_users", "scim_managed")
    op.drop_column("app_users", "scim_external_id")
