"""orders: stock holds, demo flag, checkout session, frozen placement; schema truth

* orders.is_demo, orders.checkout_session_id, orders.hold_expires_at, orders.placement_json
* reservations.order_line_id is no longer unique: a line may be held across locations
* outbox_messages (PostgreSQL): the duplicate unnamed unique constraint is dropped
* shipments: ix_shipments_package_id becomes the unique index the model declares
  (duplicate rows per package are removed first, keeping the earliest)

Revision ID: f3b8c2a91d07
Revises: d5f0a71b93c2
Create Date: 2026-09-17
"""
from alembic import op
import sqlalchemy as sa

revision = "f3b8c2a91d07"
down_revision = "d5f0a71b93c2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("orders", sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("orders", sa.Column("checkout_session_id", sa.String(120), nullable=True))
    op.add_column("orders", sa.Column("hold_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("placement_json", sa.Text(), nullable=False, server_default="{}"))
    op.create_index("ix_orders_checkout_session_id", "orders", ["checkout_session_id"], unique=False)
    op.create_index("ix_orders_hold_expires_at", "orders", ["hold_expires_at"], unique=False)

    op.drop_index("ix_reservations_order_line_id", table_name="reservations")
    op.create_index("ix_reservations_order_line_id", "reservations", ["order_line_id"], unique=False)

    op.execute(sa.text(
        "DELETE FROM shipments WHERE id IN ("
        " SELECT s.id FROM shipments s JOIN shipments t ON s.package_id = t.package_id"
        " AND (t.created_at < s.created_at OR (t.created_at = s.created_at AND t.id < s.id)))"
    ))
    op.drop_index("ix_shipments_package_id", table_name="shipments")
    op.create_index("ix_shipments_package_id", "shipments", ["package_id"], unique=True)
    if op.get_bind().dialect.name == "postgresql":
        # The unnamed unique constraint from the first shipments migration duplicates the
        # unique index above; PostgreSQL named it, so it can go.
        op.execute(sa.text("ALTER TABLE shipments DROP CONSTRAINT IF EXISTS shipments_package_id_key"))
        # Same for the outbox: ix_outbox_messages_idempotency_key is already unique.
        op.execute(sa.text("ALTER TABLE outbox_messages DROP CONSTRAINT IF EXISTS outbox_messages_idempotency_key_key"))


def downgrade():
    op.drop_index("ix_shipments_package_id", table_name="shipments")
    op.create_index("ix_shipments_package_id", "shipments", ["package_id"], unique=False)
    op.drop_index("ix_reservations_order_line_id", table_name="reservations")
    op.create_index("ix_reservations_order_line_id", "reservations", ["order_line_id"], unique=True)
    op.drop_index("ix_orders_hold_expires_at", table_name="orders")
    op.drop_index("ix_orders_checkout_session_id", table_name="orders")
    with op.batch_alter_table("orders") as batch:
        batch.drop_column("placement_json")
        batch.drop_column("hold_expires_at")
        batch.drop_column("checkout_session_id")
        batch.drop_column("is_demo")
