"""add shipping records

Revision ID: c31c8ad4c7f0
Revises: 8aa1d2c34110
Create Date: 2026-08-31
"""
from alembic import op
import sqlalchemy as sa

revision = "c31c8ad4c7f0"
down_revision = "8aa1d2c34110"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "shipments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("package_id", sa.String(36), sa.ForeignKey("packages.id"), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("external_shipment_id", sa.String(120), nullable=True),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("selected_rate_id", sa.String(120), nullable=True),
        sa.Column("carrier", sa.String(80), nullable=True),
        sa.Column("service", sa.String(120), nullable=True),
        sa.Column("tracking_code", sa.String(180), nullable=True),
        sa.Column("label_url", sa.Text(), nullable=True),
        sa.Column("label_zpl_url", sa.Text(), nullable=True),
        sa.Column("postage_amount", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(8), nullable=True),
        sa.Column("rates_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("package_id"),
        sa.UniqueConstraint("external_shipment_id"),
    )
    op.create_index("ix_shipments_package_id", "shipments", ["package_id"])
    op.create_index("ix_shipments_state", "shipments", ["state"])
    op.create_index("ix_shipments_tracking_code", "shipments", ["tracking_code"])
    op.add_column("courier_pickups", sa.Column("external_pickup_id", sa.String(120), nullable=True))
    op.add_column("courier_pickups", sa.Column("external_status", sa.String(60), nullable=True))
    op.add_column("courier_pickups", sa.Column("external_rates_json", sa.Text(), nullable=False, server_default="[]"))
    op.create_index("uq_courier_pickups_external_pickup_id", "courier_pickups", ["external_pickup_id"], unique=True)


def downgrade():
    op.drop_index("uq_courier_pickups_external_pickup_id", table_name="courier_pickups")
    op.drop_column("courier_pickups", "external_rates_json")
    op.drop_column("courier_pickups", "external_status")
    op.drop_column("courier_pickups", "external_pickup_id")
    op.drop_index("ix_shipments_tracking_code", table_name="shipments")
    op.drop_index("ix_shipments_state", table_name="shipments")
    op.drop_index("ix_shipments_package_id", table_name="shipments")
    op.drop_table("shipments")
