"""add per-device edge credentials

Revision ID: e47d92b4c610
Revises: c31c8ad4c7f0
Create Date: 2026-08-31
"""
from alembic import op
import sqlalchemy as sa

revision = "e47d92b4c610"
down_revision = "c31c8ad4c7f0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "edge_credentials",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("device_id", sa.String(80), sa.ForeignKey("devices.id"), nullable=False),
        sa.Column("site", sa.String(80), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("device_id", "site", name="uq_edge_credential_device_site"),
    )
    op.create_index("ix_edge_credentials_device_id", "edge_credentials", ["device_id"])
    op.create_index("ix_edge_credentials_site", "edge_credentials", ["site"])
    op.create_index("ix_edge_credentials_enabled", "edge_credentials", ["enabled"])


def downgrade():
    op.drop_index("ix_edge_credentials_enabled", table_name="edge_credentials")
    op.drop_index("ix_edge_credentials_site", table_name="edge_credentials")
    op.drop_index("ix_edge_credentials_device_id", table_name="edge_credentials")
    op.drop_table("edge_credentials")
