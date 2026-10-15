"""orders: PayPal Orders v2 ids

* orders.paypal_order_id: the PayPal order a PAYPAL web order is paid through
* orders.paypal_capture_id: the capture that moved the money (refunds and tracking need it)
* orders.paypal_status: PayPal's last word on the payment (CREATED, APPROVED, COMPLETED, PENDING,
  REFUNDED, ...)
* orders.paypal_tracking_id / paypal_refund_id: what the shop pushed back to PayPal

Revision ID: c4d8e2f6a1b9
Revises: b2e6d4f1a8c3
Create Date: 2026-10-15
"""
from alembic import op
import sqlalchemy as sa

revision = "c4d8e2f6a1b9"
down_revision = "b2e6d4f1a8c3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("orders", sa.Column("paypal_order_id", sa.String(64), nullable=True))
    op.add_column("orders", sa.Column("paypal_capture_id", sa.String(64), nullable=True))
    op.add_column("orders", sa.Column("paypal_status", sa.String(40), nullable=True))
    op.add_column("orders", sa.Column("paypal_tracking_id", sa.String(160), nullable=True))
    op.add_column("orders", sa.Column("paypal_refund_id", sa.String(64), nullable=True))
    op.create_index("ix_orders_paypal_order_id", "orders", ["paypal_order_id"])
    op.create_index("ix_orders_paypal_capture_id", "orders", ["paypal_capture_id"])


def downgrade():
    op.drop_index("ix_orders_paypal_capture_id", table_name="orders")
    op.drop_index("ix_orders_paypal_order_id", table_name="orders")
    with op.batch_alter_table("orders") as batch:
        for name in ("paypal_refund_id", "paypal_tracking_id", "paypal_status", "paypal_capture_id", "paypal_order_id"):
            batch.drop_column(name)
