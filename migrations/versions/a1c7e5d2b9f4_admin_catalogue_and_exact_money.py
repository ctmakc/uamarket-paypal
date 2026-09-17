"""admin catalogue: images, taxonomy tables, customs fields, exact money

* variants: option_label_uk, cost_cad, fibre_content, country_of_origin, hs_code,
  length_cm / width_cm / height_cm
* products: size_chart_json
* inventory_events: note, actor (reason text for receipts and adjustments)
* new tables: product_images, categories, collections, shop_settings, order_notes
* categories and collections are seeded with the lists the code carried until now
* money columns move from FLOAT to NUMERIC(10,2). A data check runs first: a value that
  does not fit NUMERIC(10,2) stops the migration with the offending table and column,
  and everything else is rounded to the cent.

Revision ID: a1c7e5d2b9f4
Revises: f3b8c2a91d07
Create Date: 2026-09-17
"""
from alembic import op
import sqlalchemy as sa

revision = "a1c7e5d2b9f4"
down_revision = "f3b8c2a91d07"
branch_labels = None
depends_on = None

MONEY = [
    ("variants", "price_cad", False),
    ("orders", "gross_amount_cad", False),
    ("orders", "subtotal_cad", True),
    ("orders", "shipping_cad", True),
    ("orders", "tax_cad", True),
    ("order_lines", "unit_price_cad", False),
    ("shipments", "postage_amount", True),
]

CATEGORIES = [
    ("women", "Women's vyshyvanky", "Жіночі вишиванки", True),
    ("men", "Men's vyshyvanky", "Чоловічі вишиванки", True),
    ("kids", "Kids", "Дитяче", True),
    ("home", "Home & table", "Дім і стіл", False),
    ("dolls", "Motanka dolls", "Ляльки-мотанки", False),
    ("ceramics", "Ceramics", "Кераміка", False),
    ("gifts", "Gifts & small things", "Подарунки та дрібнички", False),
]

COLLECTIONS = [
    ("heritage", "Heritage", "Спадщина",
     "Hand-embroidered and hand-made in a named Ukrainian village or workshop. Each piece says who made it.",
     "Вишито та зроблено руками в конкретному українському селі чи майстерні. Кожна річ каже, хто її зробив."),
    ("everyday", "Everyday", "Щодня",
     "Machine-embroidered shirts and blouses sewn in Ukraine for daily wear: washable, priced for a wardrobe.",
     "Машинна вишивка, пошито в Україні для щоденного носіння: переться, ціна для гардероба."),
    ("home", "Home", "Дім",
     "Rushnyky, runners, ceramics and the things a Ukrainian table is set with.",
     "Рушники, доріжки, кераміка та все, чим накривають український стіл."),
    ("kids", "Kids", "Дітям",
     "Shirts and dolls sized for children, made to survive a festival day.",
     "Сорочки та ляльки дитячих розмірів, розраховані на цілий фестивальний день."),
    ("gifts", "Gifts", "Подарунки",
     "Small things that travel well in an envelope or a coat pocket.",
     "Дрібнички, що добре їдуть у конверті чи в кишені пальта."),
]


def upgrade():
    bind = op.get_bind()

    with op.batch_alter_table("variants") as batch:
        batch.add_column(sa.Column("option_label_uk", sa.String(120), nullable=True))
        batch.add_column(sa.Column("cost_cad", sa.Numeric(10, 2), nullable=True))
        batch.add_column(sa.Column("fibre_content", sa.String(240), nullable=True))
        batch.add_column(sa.Column("country_of_origin", sa.String(2), nullable=True))
        batch.add_column(sa.Column("hs_code", sa.String(20), nullable=True))
        batch.add_column(sa.Column("length_cm", sa.Numeric(7, 1), nullable=True))
        batch.add_column(sa.Column("width_cm", sa.Numeric(7, 1), nullable=True))
        batch.add_column(sa.Column("height_cm", sa.Numeric(7, 1), nullable=True))
    with op.batch_alter_table("products") as batch:
        batch.add_column(sa.Column("size_chart_json", sa.Text(), nullable=True))
    with op.batch_alter_table("inventory_events") as batch:
        batch.add_column(sa.Column("note", sa.Text(), nullable=True))
        batch.add_column(sa.Column("actor", sa.String(120), nullable=True))

    op.create_table(
        "product_images",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("product_id", sa.String(36), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("alt_en", sa.String(300), nullable=False),
        sa.Column("alt_uk", sa.String(300), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("widths", sa.String(60), nullable=False),
        sa.Column("original_name", sa.String(200), nullable=False),
        sa.Column("bytes_in", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_product_images_product_id", "product_images", ["product_id"], unique=False)

    categories = op.create_table(
        "categories",
        sa.Column("slug", sa.String(60), primary_key=True),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("title_uk", sa.String(120), nullable=False),
        sa.Column("garment", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    collections = op.create_table(
        "collections",
        sa.Column("slug", sa.String(60), primary_key=True),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("title_uk", sa.String(120), nullable=False),
        sa.Column("lede", sa.Text(), nullable=False),
        sa.Column("lede_uk", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "shop_settings",
        sa.Column("key", sa.String(80), primary_key=True),
        sa.Column("value_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "order_notes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("author", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_order_notes_order_id", "order_notes", ["order_id"], unique=False)
    op.create_index("ix_order_notes_created_at", "order_notes", ["created_at"], unique=False)

    op.bulk_insert(categories, [
        {"slug": s, "title": t, "title_uk": tu, "garment": g, "position": i, "active": True}
        for i, (s, t, tu, g) in enumerate(CATEGORIES)
    ])
    op.bulk_insert(collections, [
        {"slug": s, "title": t, "title_uk": tu, "lede": l, "lede_uk": lu, "position": i, "active": True}
        for i, (s, t, tu, l, lu) in enumerate(COLLECTIONS)
    ])

    # Data check before money becomes NUMERIC(10,2): the largest value that fits is
    # 99,999,999.99. Anything larger is a data error a person has to look at.
    for table, column, _nullable in MONEY:
        too_big = bind.execute(sa.text(
            f"SELECT COUNT(*) FROM {table} WHERE {column} IS NOT NULL AND ABS({column}) >= 100000000"
        )).scalar()
        if too_big:
            raise RuntimeError(f"{table}.{column}: {too_big} value(s) do not fit NUMERIC(10,2); fix them first")
        op.execute(sa.text(f"UPDATE {table} SET {column} = ROUND({column}, 2) WHERE {column} IS NOT NULL")
                   if bind.dialect.name != "postgresql" else
                   sa.text(f"UPDATE {table} SET {column} = ROUND({column}::numeric, 2) WHERE {column} IS NOT NULL"))
    for table, column, nullable in MONEY:
        with op.batch_alter_table(table) as batch:
            kwargs = {"postgresql_using": f"ROUND({column}::numeric, 2)"} if bind.dialect.name == "postgresql" else {}
            batch.alter_column(column, existing_type=sa.Float(), type_=sa.Numeric(10, 2),
                               existing_nullable=nullable, **kwargs)


def downgrade():
    bind = op.get_bind()
    for table, column, nullable in MONEY:
        with op.batch_alter_table(table) as batch:
            kwargs = {"postgresql_using": f"{column}::double precision"} if bind.dialect.name == "postgresql" else {}
            batch.alter_column(column, existing_type=sa.Numeric(10, 2), type_=sa.Float(),
                               existing_nullable=nullable, **kwargs)
    op.drop_index("ix_order_notes_created_at", table_name="order_notes")
    op.drop_index("ix_order_notes_order_id", table_name="order_notes")
    op.drop_table("order_notes")
    op.drop_table("shop_settings")
    op.drop_table("collections")
    op.drop_table("categories")
    op.drop_index("ix_product_images_product_id", table_name="product_images")
    op.drop_table("product_images")
    with op.batch_alter_table("inventory_events") as batch:
        batch.drop_column("actor")
        batch.drop_column("note")
    with op.batch_alter_table("products") as batch:
        batch.drop_column("size_chart_json")
    with op.batch_alter_table("variants") as batch:
        for column in ("height_cm", "width_cm", "length_cm", "hs_code", "country_of_origin",
                       "fibre_content", "cost_cad", "option_label_uk"):
            batch.drop_column(column)
