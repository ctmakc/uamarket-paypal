"""order pipeline safety: label-buy in-flight marker and exception resolution

Adds:
  * shipments.purchase_started_at — written and committed before the EasyPost buy call, so a
    crashed or timed-out purchase is recoverable instead of being bought a second time.
  * exceptions.resolution_note / resolved_by / resolved_at — an exception can now be closed by an
    operator, which is what makes the dashboard's open count fall as well as rise.

Revision ID: b7d4e1f80c25
Revises: a9f3c2d1e0b4
Create Date: 2026-09-02
"""
from alembic import op
import sqlalchemy as sa

revision = "b7d4e1f80c25"
down_revision = "a9f3c2d1e0b4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("shipments", sa.Column("purchase_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("exceptions", sa.Column("resolution_note", sa.Text(), nullable=True))
    op.add_column("exceptions", sa.Column("resolved_by", sa.String(120), nullable=True))
    op.add_column("exceptions", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("exceptions", "resolved_at")
    op.drop_column("exceptions", "resolved_by")
    op.drop_column("exceptions", "resolution_note")
    op.drop_column("shipments", "purchase_started_at")
