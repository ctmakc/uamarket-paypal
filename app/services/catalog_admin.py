"""The owner's side of the catalogue: makers, products, variants, photos and stock.

Rules this module keeps:
  * nothing is ever deleted that an order or the ledger may point at: makers, products and
    variants are retired (active=false) and can be brought back;
  * stock changes only through ledger entries (RECEIVED, ADJUSTMENT) with a reason;
  * a product goes on sale only through `activate`, which refuses with a list of what is
    missing. The list is longer once SHOP_CATALOGUE_STATUS=live (photos with alt text, stock,
    a size chart for garments), because that is when a shopper pays for what the page says.
"""
from __future__ import annotations

import json
import re
import secrets
import unicodedata

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    InventoryBalance, InventoryEvent, Location, Maker, Product, ProductImage, ShopSetting, Variant, now_utc,
)
from .catalog import (
    ORIGINS, SELLABLE_LOCATION_KINDS, _availability_map, _loads, category_rows, collection_rows, image_dict,
    size_chart_for,
)
from .inventory import get_balance, receive

DEFAULT_RECEIVE_LOCATION = "A-LANE-01"
ADJUST_REASONS = {
    "COUNT_CORRECTION": ("Stock count correction", "Виправлення після перерахунку"),
    "DAMAGED": ("Damaged", "Пошкоджено"),
    "LOST": ("Lost or missing", "Загублено"),
    "RETURNED": ("Returned by a buyer", "Повернення від покупця"),
    "SAMPLE": ("Taken as a sample or for photos", "Взято як зразок чи для фото"),
    "FOUND": ("Found", "Знайдено"),
}


class AdminError(ValueError):
    def __init__(self, message: str, *, code: str = "invalid", status: int = 400, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.status = status
        self.details = details or {}


# ------------------------------------------------------------------ small helpers

TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "h", "ґ": "g", "д": "d", "е": "e", "є": "ie", "ж": "zh", "з": "z",
    "и": "y", "і": "i", "ї": "i", "й": "i", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p",
    "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ь": "", "ю": "iu", "я": "ia", "'": "", "’": "", "ʼ": "",
}


def slugify(text: str) -> str:
    text = "".join(TRANSLIT.get(ch, ch) for ch in (text or "").lower())
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:120]


SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SKU_RE = re.compile(r"^[A-Z0-9][A-Z0-9-]{1,79}$")


def clean_slug(value: str | None, fallback: str) -> str:
    slug = (value or "").strip().lower() or slugify(fallback)
    if not slug or not SLUG_RE.match(slug):
        raise AdminError("The address name may use a–z, 0–9 and hyphens only", code="slug")
    return slug


def _text(value, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:limit] if text else None


def ean13_check_digit(first12: str) -> str:
    total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(first12))
    return str((10 - total % 10) % 10)


def new_barcode(db: Session) -> str:
    """An EAN-13 in the 200–299 in-store range (GS1 "restricted circulation"), unique in the shop."""
    for _ in range(50):
        body = "2" + str(secrets.randbelow(10)) + "".join(str(secrets.randbelow(10)) for _ in range(10))
        code = body + ean13_check_digit(body)
        if not db.scalar(select(Variant.id).where(Variant.barcode == code)):
            return code
    raise AdminError("Could not allocate a barcode", code="internal", status=500)


def new_sku(db: Session, product: Product) -> str:
    base = re.sub(r"[^A-Z0-9-]", "", product.slug.upper())[:70] or "SKU"
    n = db.scalar(select(func.count()).select_from(Variant).where(Variant.product_id == product.id)) or 0
    for i in range(n + 1, n + 200):
        sku = f"{base}-{i:02d}"
        if not db.scalar(select(Variant.id).where(Variant.sku == sku)):
            return sku
    raise AdminError("Could not allocate a SKU", code="internal", status=500)


def catalogue_live() -> bool:
    from .storefront import catalogue_live as live
    return live()


# ------------------------------------------------------------------ makers

MAKER_FIELDS = {
    "name": 200, "name_uk": 200, "region": 200, "region_uk": 200, "craft": 200, "craft_uk": 200,
    "story": 5000, "story_uk": 5000, "image_url": 400,
}


def maker_admin_dict(db: Session, m: Maker) -> dict:
    count = db.scalar(select(func.count()).select_from(Product).where(Product.maker_id == m.id)) or 0
    return {
        "id": m.id, "slug": m.slug, "name": m.name, "name_uk": m.name_uk, "region": m.region, "region_uk": m.region_uk,
        "country": m.country, "craft": m.craft, "craft_uk": m.craft_uk, "story": m.story, "story_uk": m.story_uk,
        "image_url": m.image_url, "founded_year": m.founded_year, "active": m.active, "position": m.position,
        "product_count": int(count),
    }


def apply_maker(db: Session, m: Maker, data: dict, *, creating: bool) -> Maker:
    if creating or "slug" in data:
        slug = clean_slug(data.get("slug"), data.get("name") or m.name or "")
        clash = db.scalar(select(Maker).where(Maker.slug == slug, Maker.id != m.id))
        if clash:
            raise AdminError(f"Another maker already uses the address name “{slug}”", code="slug_taken", status=409)
        m.slug = slug
    for key, limit in MAKER_FIELDS.items():
        if key in data:
            value = _text(data[key], limit)
            if key in {"name", "region", "craft", "story"}:
                setattr(m, key, value or "")
            else:
                setattr(m, key, value)
    if "country" in data:
        country = (data.get("country") or "UA").strip().upper()
        if not re.match(r"^[A-Z]{2}$", country):
            raise AdminError("Country is a two-letter code such as UA or CA", code="country")
        m.country = country
    if "founded_year" in data:
        year = data.get("founded_year")
        if year in (None, ""):
            m.founded_year = None
        else:
            try:
                year = int(year)
            except (TypeError, ValueError):
                raise AdminError("Founded year is a number", code="founded_year")
            if not 1500 <= year <= now_utc().year:
                raise AdminError("Founded year is out of range", code="founded_year")
            m.founded_year = year
    if "position" in data and data["position"] not in (None, ""):
        m.position = int(data["position"])
    if not (m.name or "").strip():
        raise AdminError("A maker needs a name", code="name")
    return m


def create_maker(db: Session, data: dict) -> Maker:
    m = Maker(active=True)
    apply_maker(db, m, data, creating=True)
    db.add(m)
    db.flush()
    return m


# ------------------------------------------------------------------ products

PRODUCT_TEXT = {
    "title": 240, "title_uk": 240, "subtitle": 240, "subtitle_uk": 240, "description": 10000,
    "description_uk": 10000, "origin_note": 240, "origin_note_uk": 240, "technique": 240, "technique_uk": 240,
    "material": 240, "material_uk": 240, "care": 400, "care_uk": 400,
}
REQUIRED_TEXT = {"title", "description"}


def validate_size_chart(chart) -> dict | None:
    if chart in (None, "", {}):
        return None
    if isinstance(chart, str):
        try:
            chart = json.loads(chart)
        except ValueError:
            raise AdminError("The size chart is not valid", code="size_chart")
    if not isinstance(chart, dict) or not isinstance(chart.get("rows", {}), dict):
        raise AdminError("The size chart is not valid", code="size_chart")
    rows = {}
    for size, measures in (chart.get("rows") or {}).items():
        size = str(size).strip()[:12]
        if not size or not isinstance(measures, dict):
            continue
        clean = {}
        for measure, value in measures.items():
            key = slugify(str(measure)).replace("-", "_")[:40]
            text = str(value).strip()[:20]
            if key and text:
                clean[key] = text
        if clean:
            rows[size] = clean
    if not rows:
        return None
    unit = "in" if str(chart.get("unit") or "cm").lower() == "in" else "cm"
    return {"unit": unit, "note": str(chart.get("note") or "")[:240], "note_uk": str(chart.get("note_uk") or "")[:240], "rows": rows}


def apply_product(db: Session, p: Product, data: dict, *, creating: bool) -> Product:
    if creating or "slug" in data:
        slug = clean_slug(data.get("slug"), data.get("title") or p.title or "")
        clash = db.scalar(select(Product).where(Product.slug == slug, Product.id != p.id))
        if clash:
            raise AdminError(f"Another product already uses the address name “{slug}”", code="slug_taken", status=409)
        p.slug = slug
    for key, limit in PRODUCT_TEXT.items():
        if key in data:
            value = _text(data[key], limit)
            setattr(p, key, (value or "") if key in REQUIRED_TEXT else value)
    if creating or "category" in data:
        cats = {c["slug"] for c in category_rows(db, include_inactive=True)}
        if data.get("category") not in cats:
            raise AdminError("Choose a category", code="category", details={"allowed": sorted(cats)})
        p.category = data["category"]
    if creating or "collection" in data:
        cols = {c["slug"] for c in collection_rows(db, include_inactive=True)}
        if data.get("collection") not in cols:
            raise AdminError("Choose a collection", code="collection", details={"allowed": sorted(cols)})
        p.collection = data["collection"]
    if creating or "origin" in data:
        origin = data.get("origin") or "MADE_UA"
        if origin not in ORIGINS:
            raise AdminError("Choose how it was made", code="origin", details={"allowed": sorted(ORIGINS)})
        p.origin = origin
    if "maker_id" in data or "maker_slug" in data:
        maker = None
        if data.get("maker_id"):
            maker = db.get(Maker, data["maker_id"])
        elif data.get("maker_slug"):
            maker = db.scalar(select(Maker).where(Maker.slug == data["maker_slug"]))
        if (data.get("maker_id") or data.get("maker_slug")) and maker is None:
            raise AdminError("That maker does not exist", code="maker")
        p.maker_id = maker.id if maker else None
    if "featured" in data:
        p.featured = bool(data["featured"])
    if "position" in data and data["position"] not in (None, ""):
        p.position = int(data["position"])
    if "size_chart" in data:
        chart = validate_size_chart(data["size_chart"])
        p.size_chart_json = json.dumps(chart, ensure_ascii=False) if chart else None
    if not (p.title or "").strip():
        raise AdminError("A product needs an English title", code="title")
    return p


def create_product(db: Session, data: dict) -> Product:
    p = Product(active=False, images_json="[]", attributes_json="{}", description="")
    apply_product(db, p, data, creating=True)
    if p.position in (None, 0):
        p.position = int(db.scalar(select(func.coalesce(func.max(Product.position), 0)).select_from(Product)) or 0) + 1
    db.add(p)
    db.flush()
    return p


# ------------------------------------------------------------------ variants

def _money_value(value, field: str, *, required: bool) -> float | None:
    if value in (None, ""):
        if required:
            raise AdminError(f"{field} is required", code=field)
        return None
    try:
        amount = round(float(str(value).replace(",", ".").replace("$", "").strip()), 2)
    except ValueError:
        raise AdminError(f"{field} must be an amount like 120.00", code=field)
    if amount < 0 or amount >= 100_000_000:
        raise AdminError(f"{field} is out of range", code=field)
    return amount


def _positive_int(value, field: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        n = int(float(str(value).strip()))
    except ValueError:
        raise AdminError(f"{field} must be a whole number", code=field)
    if n <= 0 or n > 1_000_000:
        raise AdminError(f"{field} must be above zero", code=field)
    return n


def _dimension(value, field: str) -> float | None:
    if value in (None, ""):
        return None
    try:
        n = round(float(str(value).replace(",", ".")), 1)
    except ValueError:
        raise AdminError(f"{field} must be a number of centimetres", code=field)
    if n <= 0 or n > 500:
        raise AdminError(f"{field} is out of range", code=field)
    return n


def apply_variant(db: Session, v: Variant, product: Product, data: dict, *, creating: bool) -> Variant:
    if "sku" in data or creating:
        sku = (data.get("sku") or "").strip().upper()
        if not sku:
            sku = v.sku if not creating else new_sku(db, product)
        if not SKU_RE.match(sku):
            raise AdminError("A SKU uses A–Z, 0–9 and hyphens", code="sku")
        clash = db.scalar(select(Variant).where(Variant.sku == sku, Variant.id != v.id))
        if clash:
            raise AdminError(f"SKU {sku} is already used", code="sku_taken", status=409)
        if not creating and sku != v.sku and _has_ledger(db, v):
            raise AdminError("This SKU already has stock history and cannot be renamed", code="sku_locked", status=409)
        v.sku = sku
    if "barcode" in data or creating:
        code = re.sub(r"\s", "", str(data.get("barcode") or ""))
        if not code:
            code = v.barcode if not creating else new_barcode(db)
        if not re.match(r"^[0-9A-Za-z-]{4,120}$", code):
            raise AdminError("The barcode may use digits, letters and hyphens", code="barcode")
        clash = db.scalar(select(Variant).where(Variant.barcode == code, Variant.id != v.id))
        if clash:
            raise AdminError(f"Barcode {code} belongs to {clash.sku}", code="barcode_taken", status=409)
        v.barcode = code
    if "option_label" in data:
        v.option_label = _text(data["option_label"], 120)
    if "option_label_uk" in data:
        v.option_label_uk = _text(data["option_label_uk"], 120)
    if "price_cad" in data or creating:
        v.price_cad = _money_value(data.get("price_cad"), "price_cad", required=False) or 0.0
    if "cost_cad" in data:
        v.cost_cad = _money_value(data.get("cost_cad"), "cost_cad", required=False)
    if "weight_g" in data:
        v.weight_g = _positive_int(data.get("weight_g"), "weight_g")
    for key in ("length_cm", "width_cm", "height_cm"):
        if key in data:
            setattr(v, key, _dimension(data.get(key), key))
    if "fibre_content" in data:
        v.fibre_content = _text(data["fibre_content"], 240)
    if "country_of_origin" in data:
        c = (data.get("country_of_origin") or "").strip().upper()
        if c and not re.match(r"^[A-Z]{2}$", c):
            raise AdminError("Country of origin is a two-letter code such as UA", code="country_of_origin")
        v.country_of_origin = c or None
    if "hs_code" in data:
        hs = re.sub(r"[\s.]", "", str(data.get("hs_code") or ""))
        if hs and not re.match(r"^[0-9]{6,10}$", hs):
            raise AdminError("An HS code has 6 to 10 digits", code="hs_code")
        v.hs_code = hs or None
    if "position" in data and data["position"] not in (None, ""):
        v.position = int(data["position"])
    label = v.option_label or "One size"
    v.name = f"{product.title} {label}".strip()[:240]
    # The storefront picker reads option/option_uk for single-axis products.
    options = _loads(v.option_json, {})
    if not any(k in options for k in ("size", "colour")):
        options = {"option": v.option_label or "", "option_uk": v.option_label_uk or v.option_label or ""}
        v.option_json = json.dumps(options, ensure_ascii=False)
    return v


def create_variant(db: Session, product: Product, data: dict) -> Variant:
    v = Variant(product_id=product.id, active=True, option_json="{}")
    if data.get("position") in (None, ""):
        v.position = int(db.scalar(select(func.count()).select_from(Variant).where(Variant.product_id == product.id)) or 0)
    apply_variant(db, v, product, data, creating=True)
    db.add(v)
    db.flush()
    return v


def _has_ledger(db: Session, v: Variant) -> bool:
    return bool(v.id and db.scalar(select(InventoryEvent.id).where(InventoryEvent.variant_id == v.id).limit(1)))


# ------------------------------------------------------------------ stock

def stock_rows(db: Session, variants: list[Variant]) -> dict[str, dict]:
    ids = [v.id for v in variants]
    out = {vid: {"on_hand": 0, "reserved": 0, "available": 0, "locations": []} for vid in ids}
    if not ids:
        return out
    rows = db.execute(
        select(InventoryBalance.variant_id, InventoryBalance.location_id, Location.kind, Location.enabled,
               InventoryBalance.qty_on_hand, InventoryBalance.qty_reserved)
        .join(Location, Location.id == InventoryBalance.location_id)
        .where(InventoryBalance.variant_id.in_(ids))
        .order_by(InventoryBalance.location_id)
    ).all()
    for vid, loc, kind, enabled, on_hand, reserved in rows:
        entry = out[vid]
        sellable = bool(enabled) and kind in SELLABLE_LOCATION_KINDS
        entry["locations"].append({"location_id": loc, "kind": kind, "sellable": sellable,
                                   "on_hand": on_hand, "reserved": reserved})
        if sellable:
            entry["on_hand"] += on_hand
            entry["reserved"] += reserved
    availability = _availability_map(db, ids)
    for vid in ids:
        out[vid]["available"] = availability[vid].qty
        out[vid]["shopper"] = availability[vid].as_dict()
    return out


def sellable_locations(db: Session) -> list[dict]:
    rows = list(db.scalars(select(Location).where(Location.enabled.is_(True)).order_by(Location.id)))
    return [{"id": r.id, "kind": r.kind, "sellable": r.kind in SELLABLE_LOCATION_KINDS} for r in rows]


def ensure_default_location(db: Session) -> str:
    if not db.get(Location, DEFAULT_RECEIVE_LOCATION):
        db.add(Location(id=DEFAULT_RECEIVE_LOCATION, kind="A_LANE"))
        db.flush()
    return DEFAULT_RECEIVE_LOCATION


def receive_stock(db: Session, *, sku: str, qty: int, location_id: str | None, note: str | None, actor: str) -> InventoryEvent:
    variant = db.scalar(select(Variant).where(Variant.sku == (sku or "").strip().upper()))
    if not variant:
        raise AdminError(f"Unknown SKU {sku}", code="sku", status=404)
    if not isinstance(qty, int) or qty <= 0 or qty > 100_000:
        raise AdminError("Quantity received must be above zero", code="qty")
    location_id = location_id or ensure_default_location(db)
    location = db.get(Location, location_id)
    if not location:
        raise AdminError("Unknown location", code="location", status=404)
    reference = f"ADMIN-RECEIPT-{now_utc():%Y%m%d%H%M%S}-{secrets.token_hex(3)}"
    receive(db, variant_id=variant.id, location_id=location_id, qty=qty, reference_id=reference)
    db.flush()
    event = db.scalar(select(InventoryEvent).where(InventoryEvent.reference_id == reference))
    event.note = _text(note, 1000)
    event.actor = actor
    return event


def adjust_stock(db: Session, *, sku: str, delta: int, location_id: str | None, reason: str, note: str | None, actor: str) -> InventoryEvent:
    variant = db.scalar(select(Variant).where(Variant.sku == (sku or "").strip().upper()))
    if not variant:
        raise AdminError(f"Unknown SKU {sku}", code="sku", status=404)
    if reason not in ADJUST_REASONS:
        raise AdminError("Choose a reason for the adjustment", code="reason", details={"allowed": sorted(ADJUST_REASONS)})
    if not isinstance(delta, int) or delta == 0 or abs(delta) > 100_000:
        raise AdminError("The change must be a whole number other than zero", code="delta")
    location_id = location_id or ensure_default_location(db)
    if not db.get(Location, location_id):
        raise AdminError("Unknown location", code="location", status=404)
    balance = get_balance(db, variant.id, location_id, lock=True)
    if balance.qty_on_hand + delta < balance.qty_reserved:
        raise AdminError(
            f"That leaves {balance.qty_on_hand + delta} on the shelf while {balance.qty_reserved} are reserved for orders",
            code="below_reserved", status=409,
        )
    balance.qty_on_hand += delta
    event = InventoryEvent(
        variant_id=variant.id, event_type="ADJUSTMENT", qty=delta,
        from_location_id=location_id if delta < 0 else None, to_location_id=location_id if delta > 0 else None,
        reference_type="ADJUSTMENT", reference_id=reason, note=_text(note, 1000), actor=actor,
    )
    db.add(event)
    db.flush()
    return event


def ledger(db: Session, variant: Variant, limit: int = 100) -> list[dict]:
    rows = list(db.scalars(select(InventoryEvent).where(InventoryEvent.variant_id == variant.id)
                           .order_by(InventoryEvent.created_at.desc()).limit(limit)))
    return [{
        "id": e.id, "type": e.event_type, "qty": e.qty, "location": e.to_location_id or e.from_location_id,
        "reference_type": e.reference_type, "reference": e.reference_id, "note": e.note, "actor": e.actor,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    } for e in rows]


# ------------------------------------------------------------------ activation

def activation_problems(db: Session, p: Product, *, live: bool | None = None) -> list[dict]:
    """What stops this product from going on sale. Empty means it may be activated."""
    live = catalogue_live() if live is None else live
    problems: list[dict] = []

    def need(code: str, en: str, uk: str, **extra):
        problems.append({"code": code, "message": en, "message_uk": uk, **extra})

    variants = list(db.scalars(select(Variant).where(Variant.product_id == p.id, Variant.active.is_(True))))
    if not (p.title or "").strip():
        need("title", "English title", "Назва англійською")
    if not variants:
        need("variants", "At least one variant (size, colour or option) that is not retired",
             "Хоча б один варіант (розмір, колір чи опція), не знятий з продажу")
    for v in variants:
        if not v.price_cad or float(v.price_cad) <= 0:
            need("price", f"Price for {v.sku}", f"Ціна для {v.sku}", sku=v.sku)
        if not v.weight_g:
            need("weight", f"Shipping weight for {v.sku}", f"Вага для відправки {v.sku}", sku=v.sku)
    if not live:
        return problems

    if not (p.title_uk or "").strip():
        need("title_uk", "Ukrainian title", "Назва українською")
    if not (p.description or "").strip() or not (p.description_uk or "").strip():
        need("description", "Description in English and Ukrainian", "Опис англійською та українською")
    for v in variants:
        if v.option_label and not v.option_label_uk:
            need("option_label_uk", f"Ukrainian label for {v.sku}", f"Українська назва варіанта {v.sku}", sku=v.sku)
    images = list(db.scalars(select(ProductImage).where(ProductImage.product_id == p.id)))
    if not images:
        need("photo", "At least one photo", "Хоча б одне фото")
    for image in images:
        if not image.alt_en.strip() or not image.alt_uk.strip():
            need("alt", "Alt text in both languages for every photo", "Опис фото обома мовами для кожного фото", image_id=image.id)
            break
    availability = _availability_map(db, [v.id for v in variants])
    if variants and not any(a.in_stock for a in availability.values()):
        need("stock", "Stock received for at least one variant", "Прийнятий товар хоча б для одного варіанта")
    garment = {c["slug"] for c in category_rows(db, include_inactive=True) if c.get("garment")}
    if p.category in garment and not size_chart_for(db, p):
        need("size_chart", "A size chart (on the product or the shop default)", "Таблиця розмірів (у товарі або загальна)")
    return problems


def activate(db: Session, p: Product) -> Product:
    problems = activation_problems(db, p)
    if problems:
        raise AdminError("This product cannot go on sale yet", code="activation", status=422, details={"problems": problems})
    p.active = True
    return p


# ------------------------------------------------------------------ images

def next_image_position(db: Session, product_id: str) -> int:
    # max() is 0 once the first photo is in, and 0 is falsy: compare with None, never `or`.
    top = db.scalar(select(func.max(ProductImage.position)).where(ProductImage.product_id == product_id))
    return 0 if top is None else int(top) + 1


def reorder_images(db: Session, product: Product, ids: list[str]) -> None:
    images = {i.id: i for i in db.scalars(select(ProductImage).where(ProductImage.product_id == product.id))}
    if set(ids) != set(images):
        raise AdminError("The new order must list every photo of this product once", code="order")
    for pos, image_id in enumerate(ids):
        images[image_id].position = pos


# ------------------------------------------------------------------ read models

def variant_admin_dict(v: Variant, stock: dict | None) -> dict:
    return {
        "id": v.id, "sku": v.sku, "barcode": v.barcode, "option_label": v.option_label, "option_label_uk": v.option_label_uk,
        "price_cad": round(float(v.price_cad or 0), 2), "cost_cad": None if v.cost_cad is None else round(float(v.cost_cad), 2),
        "weight_g": v.weight_g, "length_cm": v.length_cm, "width_cm": v.width_cm, "height_cm": v.height_cm,
        "fibre_content": v.fibre_content, "country_of_origin": v.country_of_origin, "hs_code": v.hs_code,
        "active": v.active, "position": v.position, "stock": stock or {"on_hand": 0, "reserved": 0, "available": 0, "locations": []},
    }


def product_admin_dict(db: Session, p: Product, *, full: bool = True) -> dict:
    variants = sorted(db.scalars(select(Variant).where(Variant.product_id == p.id)), key=lambda v: (not v.active, v.position, v.sku))
    stock = stock_rows(db, variants)
    maker = db.get(Maker, p.maker_id) if p.maker_id else None
    images = list(db.scalars(select(ProductImage).where(ProductImage.product_id == p.id).order_by(ProductImage.position, ProductImage.created_at)))
    active_variants = [v for v in variants if v.active]
    prices = [float(v.price_cad or 0) for v in active_variants]
    d = {
        "id": p.id, "slug": p.slug, "title": p.title, "title_uk": p.title_uk, "category": p.category,
        "collection": p.collection, "origin": p.origin, "active": p.active, "featured": p.featured,
        "maker": {"id": maker.id, "slug": maker.slug, "name": maker.name, "name_uk": maker.name_uk} if maker else None,
        "price_from_cad": round(min(prices), 2) if prices else None,
        "price_to_cad": round(max(prices), 2) if prices else None,
        "variant_count": len(active_variants),
        "on_hand": sum(stock[v.id]["on_hand"] for v in active_variants),
        "available": sum(stock[v.id]["available"] for v in active_variants),
        "thumb": image_dict(images[0]) if images else None,
        "photo_count": len(images),
        "position": p.position,
    }
    if full:
        d.update({
            "subtitle": p.subtitle, "subtitle_uk": p.subtitle_uk, "description": p.description, "description_uk": p.description_uk,
            "origin_note": p.origin_note, "origin_note_uk": p.origin_note_uk, "technique": p.technique, "technique_uk": p.technique_uk,
            "material": p.material, "material_uk": p.material_uk, "care": p.care, "care_uk": p.care_uk,
            "size_chart": _loads(p.size_chart_json, None),
            "size_chart_effective": size_chart_for(db, p),
            "variants": [variant_admin_dict(v, stock[v.id]) for v in variants],
            "images": [image_dict(i) for i in images],
            "problems": activation_problems(db, p),
            "catalogue_live": catalogue_live(),
        })
    return d


def set_setting(db: Session, key: str, value) -> None:
    row = db.get(ShopSetting, key)
    if row is None:
        row = ShopSetting(key=key)
        db.add(row)
    row.value_json = json.dumps(value, ensure_ascii=False)
    row.updated_at = now_utc()
