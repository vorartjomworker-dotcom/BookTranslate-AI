"""add vision OIDC and audit

Revision ID: 20260813_0008
Revises: 20260813_0007
Create Date: 2026-08-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260813_0008"
down_revision: Union[str, None] = "20260813_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("app_users", sa.Column("oidc_issuer", sa.String(length=500), nullable=True))
    op.add_column("app_users", sa.Column("oidc_subject", sa.String(length=500), nullable=True))
    op.create_index("ix_app_users_oidc_issuer", "app_users", ["oidc_issuer"], unique=False)
    op.create_index("ix_app_users_oidc_subject", "app_users", ["oidc_subject"], unique=False)
    op.create_unique_constraint("uq_app_user_oidc_identity", "app_users", ["oidc_issuer", "oidc_subject"])

    op.create_table(
        "vision_extractions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("regions_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("raw_response_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("request_id", sa.String(length=200), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vision_extractions_asset_id", "vision_extractions", ["asset_id"], unique=False)
    op.create_index("ix_vision_extractions_provider", "vision_extractions", ["provider"], unique=False)
    op.create_index("ix_vision_extractions_status", "vision_extractions", ["status"], unique=False)

    op.create_table(
        "vision_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("book_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("total_assets", sa.Integer(), nullable=False),
        sa.Column("completed_assets", sa.Integer(), nullable=False),
        sa.Column("failed_assets", sa.Integer(), nullable=False),
        sa.Column("current_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vision_jobs_book_id", "vision_jobs", ["book_id"], unique=False)
    op.create_index("ix_vision_jobs_asset_id", "vision_jobs", ["asset_id"], unique=False)
    op.create_index("ix_vision_jobs_status", "vision_jobs", ["status"], unique=False)

    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_email", sa.String(length=320), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=80), nullable=False),
        sa.Column("resource_id", sa.String(length=200), nullable=True),
        sa.Column("request_id", sa.String(length=100), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["app_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_actor_user_id", "audit_events", ["actor_user_id"], unique=False)
    op.create_index("ix_audit_events_actor_email", "audit_events", ["actor_email"], unique=False)
    op.create_index("ix_audit_events_action", "audit_events", ["action"], unique=False)
    op.create_index("ix_audit_events_resource_type", "audit_events", ["resource_type"], unique=False)
    op.create_index("ix_audit_events_request_id", "audit_events", ["request_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_audit_events_request_id", table_name="audit_events")
    op.drop_index("ix_audit_events_resource_type", table_name="audit_events")
    op.drop_index("ix_audit_events_action", table_name="audit_events")
    op.drop_index("ix_audit_events_actor_email", table_name="audit_events")
    op.drop_index("ix_audit_events_actor_user_id", table_name="audit_events")
    op.drop_table("audit_events")

    op.drop_index("ix_vision_jobs_status", table_name="vision_jobs")
    op.drop_index("ix_vision_jobs_asset_id", table_name="vision_jobs")
    op.drop_index("ix_vision_jobs_book_id", table_name="vision_jobs")
    op.drop_table("vision_jobs")

    op.drop_index("ix_vision_extractions_status", table_name="vision_extractions")
    op.drop_index("ix_vision_extractions_provider", table_name="vision_extractions")
    op.drop_index("ix_vision_extractions_asset_id", table_name="vision_extractions")
    op.drop_table("vision_extractions")

    op.drop_constraint("uq_app_user_oidc_identity", "app_users", type_="unique")
    op.drop_index("ix_app_users_oidc_subject", table_name="app_users")
    op.drop_index("ix_app_users_oidc_issuer", table_name="app_users")
    op.drop_column("app_users", "oidc_subject")
    op.drop_column("app_users", "oidc_issuer")
