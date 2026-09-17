"""Public catalogue read model for the storefront.

Everything here is read-only and safe to expose without authentication: it never
returns warehouse locations, reservations or cost data — only what a shopper may see.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import search
from ..models import Category, Collection, InventoryBalance, Location, Maker, Product, ProductImage, ShopSetting, Variant

# Locations that count as sellable stock. Exception shelves never sell.
SELLABLE_LOCATION_KINDS = ("A_LANE", "B_BIN", "RESERVE")
LOW_STOCK_AT = 2

# The lists below seed the `categories` and `collections` tables (migration a1c7e5d2b9f4 and
# ensure_taxonomy). The storefront reads the tables; these constants are only the seed and the
# fallback for a database that has not been seeded.
CATEGORIES: list[dict] = [
    {"slug": "women", "title": "Women's vyshyvanky", "title_uk": "Жіночі вишиванки", "garment": True},
    {"slug": "men", "title": "Men's vyshyvanky", "title_uk": "Чоловічі вишиванки", "garment": True},
    {"slug": "kids", "title": "Kids", "title_uk": "Дитяче", "garment": True},
    {"slug": "home", "title": "Home & table", "title_uk": "Дім і стіл"},
    {"slug": "dolls", "title": "Motanka dolls", "title_uk": "Ляльки-мотанки"},
    {"slug": "ceramics", "title": "Ceramics", "title_uk": "Кераміка"},
    {"slug": "gifts", "title": "Gifts & small things", "title_uk": "Подарунки та дрібнички"},
]

COLLECTIONS: list[dict] = [
    {
        "slug": "heritage",
        "title": "Heritage",
        "title_uk": "Спадщина",
        "lede": "Hand-embroidered and hand-made in a named Ukrainian village or workshop. Each piece says who made it.",
        "lede_uk": "Вишито та зроблено руками в конкретному українському селі чи майстерні. Кожна річ каже, хто її зробив.",
    },
    {
        "slug": "everyday",
        "title": "Everyday",
        "title_uk": "Щодня",
        "lede": "Machine-embroidered shirts and blouses sewn in Ukraine for daily wear: washable, priced for a wardrobe.",
        "lede_uk": "Машинна вишивка, пошито в Україні для щоденного носіння: переться, ціна для гардероба.",
    },
    {
        "slug": "home",
        "title": "Home",
        "title_uk": "Дім",
        "lede": "Rushnyky, runners, ceramics and the things a Ukrainian table is set with.",
        "lede_uk": "Рушники, доріжки, кераміка та все, чим накривають український стіл.",
    },
    {
        "slug": "kids",
        "title": "Kids",
        "title_uk": "Дітям",
        "lede": "Shirts and dolls sized for children, made to survive a festival day.",
        "lede_uk": "Сорочки та ляльки дитячих розмірів, розраховані на цілий фестивальний день.",
    },
    {
        "slug": "gifts",
        "title": "Gifts",
        "title_uk": "Подарунки",
        "lede": "Small things that travel well in an envelope or a coat pocket.",
        "lede_uk": "Дрібнички, що добре їдуть у конверті чи в кишені пальта.",
    },
]

ORIGINS: dict[str, dict] = {
    "HANDMADE_UA": {"label": "Hand-made in Ukraine", "label_uk": "Зроблено руками в Україні"},
    "MADE_UA": {"label": "Made in Ukraine", "label_uk": "Зроблено в Україні"},
    "DESIGNED_UA": {"label": "Designed in Ukraine, made abroad", "label_uk": "Розроблено в Україні, виготовлено за кордоном"},
}


class CatalogError(RuntimeError):
    pass


@dataclass
class Availability:
    qty: int

    @property
    def in_stock(self) -> bool:
        return self.qty > 0

    @property
    def low(self) -> bool:
        return 0 < self.qty <= LOW_STOCK_AT

    def as_dict(self) -> dict:
        # Coarse on purpose: a shop must not promise a live quantity it cannot guarantee.
        return {"in_stock": self.in_stock, "low": self.low}


def _availability_map(db: Session, variant_ids: list[str]) -> dict[str, Availability]:
    if not variant_ids:
        return {}
    rows = db.execute(
        select(
            InventoryBalance.variant_id,
            func.coalesce(func.sum(InventoryBalance.qty_on_hand - InventoryBalance.qty_reserved), 0),
        )
        .join(Location, Location.id == InventoryBalance.location_id)
        .where(
            InventoryBalance.variant_id.in_(variant_ids),
            Location.enabled.is_(True),
            Location.kind.in_(SELLABLE_LOCATION_KINDS),
        )
        .group_by(InventoryBalance.variant_id)
    ).all()
    out = {vid: Availability(0) for vid in variant_ids}
    for vid, qty in rows:
        out[vid] = Availability(max(int(qty or 0), 0))
    return out


def variant_availability(db: Session, variant_id: str) -> Availability:
    return _availability_map(db, [variant_id])[variant_id]


def _loads(text: str | None, default):
    try:
        return json.loads(text) if text else default
    except ValueError:
        return default


def maker_dict(m: Maker) -> dict:
    return {
        "slug": m.slug,
        "name": m.name,
        "name_uk": m.name_uk,
        "region": m.region,
        "region_uk": m.region_uk,
        "country": m.country,
        "craft": m.craft,
        "craft_uk": m.craft_uk,
        "story": m.story,
        "story_uk": m.story_uk,
        "image_url": m.image_url,
        "founded_year": m.founded_year,
    }


def variant_dict(v: Variant, availability: Availability | None) -> dict:
    return {
        "sku": v.sku,
        "label": v.option_label or v.name,
        "label_uk": v.option_label_uk,
        "options": _loads(v.option_json, {}),
        "price_cad": round(float(v.price_cad), 2),
        "weight_g": v.weight_g,
        "availability": (availability or Availability(0)).as_dict(),
    }


def media_url(image: ProductImage, width: int) -> str:
    return f"/media/products/{image.product_id}/{image.id}-{width}.webp"


def image_dict(image: ProductImage) -> dict:
    widths = [int(w) for w in image.widths.split(",") if w.strip()]
    medium = min(widths, key=lambda w: abs(w - 960)) if widths else 960
    return {
        "id": image.id,
        "src": media_url(image, medium),
        "srcset": ", ".join(f"{media_url(image, w)} {w}w" for w in widths),
        "width": image.width,
        "height": image.height,
        "alt": image.alt_en,
        "alt_uk": image.alt_uk,
        "position": image.position,
    }


def images_map(db: Session, product_ids: list[str]) -> dict[str, list[ProductImage]]:
    out: dict[str, list[ProductImage]] = {pid: [] for pid in product_ids}
    if not product_ids:
        return out
    for image in db.scalars(select(ProductImage).where(ProductImage.product_id.in_(product_ids))
                            .order_by(ProductImage.position, ProductImage.created_at)):
        out.setdefault(image.product_id, []).append(image)
    return out


def setting(db: Session, key: str, default=None):
    row = db.get(ShopSetting, key)
    if row is None:
        return default
    return _loads(row.value_json, default)


def size_chart_for(db: Session, p: Product) -> dict | None:
    """The product's own chart, else the shop-wide default, else None. Empty charts count as none."""
    own = _loads(p.size_chart_json, None)
    if isinstance(own, dict) and own.get("rows"):
        return own
    default = setting(db, "size_chart_default")
    if isinstance(default, dict) and default.get("rows"):
        return default
    return None


def _chart_attributes(chart: dict | None) -> dict:
    """The chart in the attribute keys web/components/SizeGuide.tsx reads (size_<S>_<measure>)."""
    if not chart:
        return {}
    out: dict = {}
    for size, measures in (chart.get("rows") or {}).items():
        if not isinstance(measures, dict):
            continue
        for measure, value in measures.items():
            text = str(value).strip()
            if text:
                out[f"size_{size}_{measure}"] = text
    if out:
        out["size_chart_unit"] = "in" if str(chart.get("unit") or "cm").lower() == "in" else "cm"
        for key in ("note", "note_uk"):
            if chart.get(key):
                out[f"size_chart_{key}"] = str(chart[key])
    return out


def product_dict(db: Session, p: Product, *, variants: list[Variant] | None = None, maker: Maker | None = None,
                 availability: dict[str, Availability] | None = None, summary: bool = False,
                 images: list[ProductImage] | None = None) -> dict:
    variants = variants if variants is not None else sorted(
        [v for v in db.scalars(select(Variant).where(Variant.product_id == p.id, Variant.active.is_(True)))],
        key=lambda v: (v.position, v.sku),
    )
    if availability is None:
        availability = _availability_map(db, [v.id for v in variants])
    if maker is None and p.maker_id:
        maker = db.get(Maker, p.maker_id)
    prices = [float(v.price_cad) for v in variants] or [0.0]
    any_stock = any(availability.get(v.id, Availability(0)).in_stock for v in variants)
    origin = ORIGINS.get(p.origin, ORIGINS["MADE_UA"])
    if images is None:
        images = images_map(db, [p.id])[p.id]
    photos = [image_dict(i) for i in images]
    d = {
        "slug": p.slug,
        "title": p.title,
        "title_uk": p.title_uk,
        "subtitle": p.subtitle,
        "subtitle_uk": p.subtitle_uk,
        "category": p.category,
        "collection": p.collection,
        "origin": p.origin,
        "origin_label": origin["label"],
        "origin_label_uk": origin["label_uk"],
        "origin_note": p.origin_note,
        "origin_note_uk": p.origin_note_uk,
        "maker": {"slug": maker.slug, "name": maker.name, "name_uk": maker.name_uk, "region": maker.region, "region_uk": maker.region_uk} if maker else None,
        "price_from_cad": round(min(prices), 2),
        "price_to_cad": round(max(prices), 2),
        # Uploaded photos win over the legacy URL fields; the storefront reads image_url and images.
        "image_url": photos[0]["src"] if photos else p.image_url,
        "images": [ph["src"] for ph in photos] if photos else _loads(p.images_json, []),
        "photos": photos,
        "featured": p.featured,
        "in_stock": any_stock,
        "variant_count": len(variants),
    }
    if not summary:
        d.update({
            "description": p.description,
            "description_uk": p.description_uk,
            "technique": p.technique,
            "technique_uk": p.technique_uk,
            "material": p.material,
            "material_uk": p.material_uk,
            "care": p.care,
            "care_uk": p.care_uk,
            # A size chart entered in the admin reaches the page through the attribute keys
            # the size guide already reads; keys the product carries itself are kept.
            "attributes": {**_chart_attributes(size_chart_for(db, p)), **_loads(p.attributes_json, {})},
            "variants": [variant_dict(v, availability.get(v.id)) for v in variants],
        })
    return d


def list_products(db: Session, *, category: str | None = None, collection: str | None = None,
                  maker: str | None = None, q: str | None = None, featured: bool | None = None,
                  in_stock: bool | None = None, sort: str = "position", limit: int = 60, offset: int = 0) -> dict:
    stmt = select(Product).where(Product.active.is_(True))
    if category:
        stmt = stmt.where(Product.category == category)
    if collection:
        stmt = stmt.where(Product.collection == collection)
    if featured is not None:
        stmt = stmt.where(Product.featured.is_(featured))
    if maker:
        m = db.scalar(select(Maker).where(Maker.slug == maker))
        if not m:
            return {"items": [], "total": 0, "limit": limit, "offset": offset}
        stmt = stmt.where(Product.maker_id == m.id)
    products = list(db.scalars(stmt))
    suggestion = None
    if q and q.strip():
        # Two languages, two alphabets, synonyms, prefixes: app/services/search.py.
        terms = search.query_terms(q)
        cats = {c["slug"]: c for c in category_rows(db)}
        cols = {c["slug"]: c for c in collection_rows(db)}
        maker_rows = {m.id: m for m in db.scalars(select(Maker).where(Maker.id.in_([p.maker_id for p in products if p.maker_id])))} if products else {}

        def _hay(p: Product) -> set[str]:
            cat = cats.get(p.category) or {}
            col = cols.get(p.collection) or {}
            maker_row = maker_rows.get(p.maker_id)
            return search.haystack_keys(
                p.title, p.title_uk, p.subtitle, p.subtitle_uk, p.technique, p.technique_uk, p.material, p.material_uk,
                p.description, p.description_uk, p.origin_note, p.origin_note_uk,
                cat.get("title"), cat.get("title_uk"), col.get("title"), col.get("title_uk"),
                maker_row.name if maker_row else None, maker_row.name_uk if maker_row else None,
                maker_row.region if maker_row else None, maker_row.region_uk if maker_row else None,
            )

        products = [p for p in products if search.matches(terms, _hay(p))] if terms else products
        if not products:
            counts = dict(db.execute(select(Product.category, func.count()).where(Product.active.is_(True)).group_by(Product.category)).all())
            candidates = [(slug, [c["title"], c["title_uk"], slug]) for slug, c in cats.items() if counts.get(slug)]
            best = search.closest(q, candidates)
            if best:
                suggestion = {"category": best, "title": cats[best]["title"], "title_uk": cats[best]["title_uk"]}
    variants = list(db.scalars(select(Variant).where(Variant.product_id.in_([p.id for p in products]), Variant.active.is_(True)))) if products else []
    by_product: dict[str, list[Variant]] = {}
    for v in variants:
        by_product.setdefault(v.product_id, []).append(v)
    availability = _availability_map(db, [v.id for v in variants])
    makers = {m.id: m for m in db.scalars(select(Maker).where(Maker.id.in_([p.maker_id for p in products if p.maker_id])))} if products else {}
    photos = images_map(db, [p.id for p in products])
    items = [
        product_dict(db, p, variants=sorted(by_product.get(p.id, []), key=lambda v: (v.position, v.sku)),
                     maker=makers.get(p.maker_id), availability=availability, summary=True, images=photos.get(p.id, []))
        for p in products
    ]
    if in_stock is not None:
        items = [i for i in items if i["in_stock"] == in_stock]
    if sort == "price_asc":
        items.sort(key=lambda i: i["price_from_cad"])
    elif sort == "price_desc":
        items.sort(key=lambda i: -i["price_to_cad"])
    elif sort == "newest":
        created = {p.slug: p.created_at for p in products}
        items.sort(key=lambda i: created[i["slug"]], reverse=True)
    else:
        pos = {p.slug: (0 if p.featured else 1, p.position, p.title) for p in products}
        items.sort(key=lambda i: pos[i["slug"]])
    total = len(items)
    out = {"items": items[offset:offset + limit], "total": total, "limit": limit, "offset": offset}
    if q:
        out["suggestion"] = suggestion
    return out


def get_product(db: Session, slug: str) -> dict:
    p = db.scalar(select(Product).where(Product.slug == slug, Product.active.is_(True)))
    if not p:
        raise CatalogError("Product not found")
    d = product_dict(db, p)
    if p.maker_id:
        siblings = [
            s for s in list_products(db, maker=d["maker"]["slug"], limit=8)["items"] if s["slug"] != p.slug
        ]
    else:
        siblings = [s for s in list_products(db, category=p.category, limit=8)["items"] if s["slug"] != p.slug]
    d["related"] = siblings[:6]
    return d


def ensure_taxonomy(db: Session) -> None:
    """Seed the category and collection tables from the constants when they are empty."""
    if db.scalar(select(func.count()).select_from(Category)) == 0:
        for i, c in enumerate(CATEGORIES):
            db.add(Category(slug=c["slug"], title=c["title"], title_uk=c["title_uk"], garment=c.get("garment", False), position=i))
    if db.scalar(select(func.count()).select_from(Collection)) == 0:
        for i, c in enumerate(COLLECTIONS):
            db.add(Collection(slug=c["slug"], title=c["title"], title_uk=c["title_uk"], lede=c["lede"], lede_uk=c["lede_uk"], position=i))
    db.flush()


def category_rows(db: Session, *, include_inactive: bool = False) -> list[dict]:
    stmt = select(Category).order_by(Category.position, Category.slug)
    if not include_inactive:
        stmt = stmt.where(Category.active.is_(True))
    rows = list(db.scalars(stmt))
    if not rows and not db.scalar(select(func.count()).select_from(Category)):
        return [{"garment": False, "active": True, **c} for c in CATEGORIES]
    return [{"slug": r.slug, "title": r.title, "title_uk": r.title_uk, "garment": bool(r.garment), "active": bool(r.active)} for r in rows]


def collection_rows(db: Session, *, include_inactive: bool = False) -> list[dict]:
    stmt = select(Collection).order_by(Collection.position, Collection.slug)
    if not include_inactive:
        stmt = stmt.where(Collection.active.is_(True))
    rows = list(db.scalars(stmt))
    if not rows and not db.scalar(select(func.count()).select_from(Collection)):
        return [{"active": True, **c} for c in COLLECTIONS]
    return [{"slug": r.slug, "title": r.title, "title_uk": r.title_uk, "lede": r.lede, "lede_uk": r.lede_uk, "active": bool(r.active)} for r in rows]


def list_collections(db: Session) -> list[dict]:
    counts = dict(db.execute(
        select(Product.collection, func.count()).where(Product.active.is_(True)).group_by(Product.collection)
    ).all())
    return [{**{k: c[k] for k in ("slug", "title", "title_uk", "lede", "lede_uk")}, "count": int(counts.get(c["slug"], 0))}
            for c in collection_rows(db)]


def list_categories(db: Session) -> list[dict]:
    counts = dict(db.execute(
        select(Product.category, func.count()).where(Product.active.is_(True)).group_by(Product.category)
    ).all())
    return [{**{k: c[k] for k in ("slug", "title", "title_uk")}, "count": int(counts.get(c["slug"], 0))}
            for c in category_rows(db)]


def list_makers(db: Session) -> list[dict]:
    makers = list(db.scalars(select(Maker).where(Maker.active.is_(True)).order_by(Maker.position, Maker.name)))
    counts = dict(db.execute(
        select(Product.maker_id, func.count()).where(Product.active.is_(True)).group_by(Product.maker_id)
    ).all())
    return [{**maker_dict(m), "product_count": int(counts.get(m.id, 0))} for m in makers]


def get_maker(db: Session, slug: str) -> dict:
    m = db.scalar(select(Maker).where(Maker.slug == slug, Maker.active.is_(True)))
    if not m:
        raise CatalogError("Maker not found")
    d = maker_dict(m)
    d["products"] = list_products(db, maker=slug, limit=100)["items"]
    return d
