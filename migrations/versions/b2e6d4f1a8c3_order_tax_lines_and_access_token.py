"""orders: named tax lines and an opaque access token for the buyer's order page

* orders.tax_lines_json: GST/HST/QST/PST lines frozen at placement
* orders.access_token: the key in the order email link and the buyer's cookie, so the
  order page URL never carries an email address. Existing orders get a fresh random token.

Revision ID: b2e6d4f1a8c3
Revises: a1c7e5d2b9f4
Create Date: 2026-09-17
"""
import secrets

from alembic import op
import sqlalchemy as sa

revision = "b2e6d4f1a8c3"
down_revision = "a1c7e5d2b9f4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("orders", sa.Column("tax_lines_json", sa.Text(), nullable=False, server_default="[]"))
    op.add_column("orders", sa.Column("access_token", sa.String(64), nullable=True))
    bind = op.get_bind()
    ids = [row[0] for row in bind.execute(sa.text("SELECT id FROM orders WHERE access_token IS NULL"))]
    for order_id in ids:
        bind.execute(sa.text("UPDATE orders SET access_token = :t WHERE id = :i"),
                     {"t": secrets.token_urlsafe(24), "i": order_id})
    op.create_index("ix_orders_access_token", "orders", ["access_token"], unique=True)


def downgrade():
    op.drop_index("ix_orders_access_token", table_name="orders")
    with op.batch_alter_table("orders") as batch:
        batch.drop_column("access_token")
        batch.drop_column("tax_lines_json")
