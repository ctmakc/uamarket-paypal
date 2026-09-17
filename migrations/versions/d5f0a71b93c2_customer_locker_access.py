"""customer locker access: a one-time bay code that belongs to a buyer's order

Until now every row in locker_access belonged to a CourierPickup, which is why the shop
could open a bay for a carrier and for nobody else. This migration makes the same table
carry the buyer's own credential:

  * kind            COURIER (the row belongs to a pickup) or CUSTOMER (it belongs to an order)
  * order_id        the web order a CUSTOMER credential opens a bay for
  * pickup_id       now nullable, because a CUSTOMER row has no pickup
  * display_code    the code a customer's order page prints back to them, erased the moment
                    the credential is used or revoked. A COURIER row leaves it empty.
  * revoked_at      set when the parcel leaves the bay; a revoked credential opens nothing
  * revoked_reason  why, in one short phrase, for the operator reading the row

Downgrade drops the four customer-only columns and makes pickup_id NOT NULL again, so it
first deletes the CUSTOMER rows: the older schema has no shape that can hold them. Any
customer code outstanding at that moment stops working, which is the honest outcome — the
code that opened the bay no longer exists anywhere.

Revision ID: d5f0a71b93c2
Revises: b7d4e1f80c25
Create Date: 2026-09-03
"""
from alembic import op
import sqlalchemy as sa

revision = "d5f0a71b93c2"
down_revision = "b7d4e1f80c25"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("locker_access") as batch:
        batch.add_column(sa.Column("kind", sa.String(20), nullable=False, server_default="COURIER"))
        batch.add_column(sa.Column("order_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("display_code", sa.String(12), nullable=True))
        batch.add_column(sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("revoked_reason", sa.String(60), nullable=True))
        batch.alter_column("pickup_id", existing_type=sa.String(36), nullable=True)
        batch.create_foreign_key("fk_locker_access_order_id", "orders", ["order_id"], ["id"])
    op.create_index(op.f("ix_locker_access_kind"), "locker_access", ["kind"], unique=False)
    op.create_index(op.f("ix_locker_access_order_id"), "locker_access", ["order_id"], unique=False)


def downgrade():
    # A CUSTOMER row has no pickup_id, so it cannot exist in the older shape of this table.
    op.execute("DELETE FROM locker_access WHERE kind = 'CUSTOMER'")
    op.drop_index(op.f("ix_locker_access_order_id"), table_name="locker_access")
    op.drop_index(op.f("ix_locker_access_kind"), table_name="locker_access")
    with op.batch_alter_table("locker_access") as batch:
        batch.alter_column("pickup_id", existing_type=sa.String(36), nullable=False)
        batch.drop_column("revoked_reason")
        batch.drop_column("revoked_at")
        batch.drop_column("display_code")
        batch.drop_column("order_id")
        batch.drop_column("kind")
