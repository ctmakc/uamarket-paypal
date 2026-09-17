"""add storefront catalogue (makers, products) and web-order fields

Revision ID: a9f3c2d1e0b4
Revises: e47d92b4c610
Create Date: 2026-09-02
"""
from alembic import op
import sqlalchemy as sa

revision = "a9f3c2d1e0b4"
down_revision = "e47d92b4c610"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "makers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("slug", sa.String(120), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("name_uk", sa.String(200), nullable=True),
        sa.Column("region", sa.String(200), nullable=False, server_default=""),
        sa.Column("region_uk", sa.String(200), nullable=True),
        sa.Column("country", sa.String(2), nullable=False, server_default="UA"),
        sa.Column("craft", sa.String(200), nullable=False, server_default=""),
        sa.Column("craft_uk", sa.String(200), nullable=True),
        sa.Column("story", sa.Text(), nullable=False, server_default=""),
        sa.Column("story_uk", sa.Text(), nullable=True),
        sa.Column("image_url", sa.String(400), nullable=True),
        sa.Column("founded_year", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_makers_slug", "makers", ["slug"], unique=True)

    op.create_table(
        "products",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("slug", sa.String(160), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("title_uk", sa.String(240), nullable=True),
        sa.Column("subtitle", sa.String(240), nullable=True),
        sa.Column("subtitle_uk", sa.String(240), nullable=True),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("description_uk", sa.Text(), nullable=True),
        sa.Column("category", sa.String(60), nullable=False),
        sa.Column("collection", sa.String(60), nullable=False),
        sa.Column("maker_id", sa.String(36), sa.ForeignKey("makers.id"), nullable=True),
        sa.Column("origin", sa.String(20), nullable=False, server_default="MADE_UA"),
        sa.Column("origin_note", sa.String(240), nullable=True),
        sa.Column("origin_note_uk", sa.String(240), nullable=True),
        sa.Column("technique", sa.String(240), nullable=True),
        sa.Column("technique_uk", sa.String(240), nullable=True),
        sa.Column("material", sa.String(240), nullable=True),
        sa.Column("material_uk", sa.String(240), nullable=True),
        sa.Column("care", sa.String(400), nullable=True),
        sa.Column("care_uk", sa.String(400), nullable=True),
        sa.Column("image_url", sa.String(400), nullable=True),
        sa.Column("images_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("attributes_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("featured", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_products_slug", "products", ["slug"], unique=True)
    op.create_index("ix_products_category", "products", ["category"])
    op.create_index("ix_products_collection", "products", ["collection"])
    op.create_index("ix_products_maker_id", "products", ["maker_id"])
    op.create_index("ix_products_origin", "products", ["origin"])
    op.create_index("ix_products_featured", "products", ["featured"])
    op.create_index("ix_products_active", "products", ["active"])

    with op.batch_alter_table("variants") as batch:
        batch.add_column(sa.Column("product_id", sa.String(36), nullable=True))
        batch.create_foreign_key("fk_variants_product_id_products", "products", ["product_id"], ["id"])
        batch.add_column(sa.Column("option_label", sa.String(120), nullable=True))
        batch.add_column(sa.Column("option_json", sa.Text(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("weight_g", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("position", sa.Integer(), nullable=False, server_default="0"))
    op.create_index("ix_variants_product_id", "variants", ["product_id"])

    with op.batch_alter_table("orders") as batch:
        batch.add_column(sa.Column("order_number", sa.String(32), nullable=True))
        batch.add_column(sa.Column("customer_email", sa.String(200), nullable=True))
        batch.add_column(sa.Column("customer_name", sa.String(200), nullable=True))
        batch.add_column(sa.Column("customer_phone", sa.String(60), nullable=True))
        batch.add_column(sa.Column("locale", sa.String(8), nullable=True))
        batch.add_column(sa.Column("fulfillment_method", sa.String(20), nullable=True))
        batch.add_column(sa.Column("ship_to_json", sa.Text(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("subtotal_cad", sa.Float(), nullable=True))
        batch.add_column(sa.Column("shipping_cad", sa.Float(), nullable=True))
        batch.add_column(sa.Column("tax_cad", sa.Float(), nullable=True))
        batch.add_column(sa.Column("tax_rate", sa.Float(), nullable=True))
        batch.add_column(sa.Column("payment_method", sa.String(20), nullable=True))
        batch.add_column(sa.Column("payment_ref", sa.String(200), nullable=True))
        batch.add_column(sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("customer_note", sa.Text(), nullable=False, server_default=""))
    op.create_index("ix_orders_order_number", "orders", ["order_number"], unique=True)
    op.create_index("ix_orders_customer_email", "orders", ["customer_email"])
    op.create_index("ix_orders_payment_ref", "orders", ["payment_ref"])


def downgrade():
    op.drop_index("ix_orders_payment_ref", table_name="orders")
    op.drop_index("ix_orders_customer_email", table_name="orders")
    op.drop_index("ix_orders_order_number", table_name="orders")
    with op.batch_alter_table("orders") as batch:
        for col in ["customer_note", "paid_at", "payment_ref", "payment_method", "tax_rate", "tax_cad", "shipping_cad",
                    "subtotal_cad", "ship_to_json", "fulfillment_method", "locale", "customer_phone", "customer_name",
                    "customer_email", "order_number"]:
            batch.drop_column(col)
    op.drop_index("ix_variants_product_id", table_name="variants")
    with op.batch_alter_table("variants") as batch:
        batch.drop_constraint("fk_variants_product_id_products", type_="foreignkey")
        for col in ["position", "weight_g", "option_json", "option_label", "product_id"]:
            batch.drop_column(col)
    for name in ["ix_products_active", "ix_products_featured", "ix_products_origin", "ix_products_maker_id",
                 "ix_products_collection", "ix_products_category", "ix_products_slug"]:
        op.drop_index(name, table_name="products")
    op.drop_table("products")
    op.drop_index("ix_makers_slug", table_name="makers")
    op.drop_table("makers")
