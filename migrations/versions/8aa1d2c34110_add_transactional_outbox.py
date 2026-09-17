"""add transactional outbox

Revision ID: 8aa1d2c34110
Revises: 59c91708be4e
Create Date: 2026-08-31 11:32:00-04:00
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "8aa1d2c34110"
down_revision: Union[str, None] = "59c91708be4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "outbox_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("topic", sa.String(length=180), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("aggregate_type", sa.String(length=60), nullable=False),
        sa.Column("aggregate_id", sa.String(length=120), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("state", sa.String(length=30), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=180), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    for col in ("topic", "event_type", "aggregate_type", "aggregate_id", "state", "idempotency_key", "created_at", "available_at"):
        op.create_index(op.f(f"ix_outbox_messages_{col}"), "outbox_messages", [col], unique=(col == "idempotency_key"))


def downgrade() -> None:
    for col in ("available_at", "created_at", "idempotency_key", "state", "aggregate_id", "aggregate_type", "event_type", "topic"):
        op.drop_index(op.f(f"ix_outbox_messages_{col}"), table_name="outbox_messages")
    op.drop_table("outbox_messages")
