"""Catalogue import from a sourcing sheet (CSV, one row per variant).

The template with every column explained is docs/catalogue-import-template.csv, and the
column reference is docs/catalogue-import.md.

Two passes, the same code:
  * dry run: every row is validated and matched, a report says per row what would be
    created, updated or refused, and nothing is written;
  * apply: the same, inside one transaction; any refused row stops the whole apply, so a
    sheet is either imported whole or not at all.

Matching: a product by `product_slug`, a variant by `sku`, a maker by `maker_slug`. An
existing row is updated with the values the sheet carries; an empty cell leaves the
stored value as it is. Stock is not imported (receive it on the stock screen, where
every unit is a ledger entry with a reason). Products are created off sale; the
`on_sale` column asks for activation, which runs the same checks as the admin button.
"""
from __future__ import annotations

import csv
import io

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Maker, Product, Variant
from .catalog_admin import (
    AdminError, activate, activation_problems, apply_maker, apply_product, apply_variant, create_maker,
    create_product, create_variant,
)

MAX_ROWS = 5000
REQUIRED_COLUMNS = {"product_slug", "sku", "title_en", "category", "collection", "price_cad"}

PRODUCT_COLUMNS = {
    "title_en": "title", "title_uk": "title_uk", "subtitle_en": "subtitle", "subtitle_uk": "subtitle_uk",
    "description_en": "description", "description_uk": "description_uk", "category": "category",
    "collection": "collection", "origin": "origin", "origin_note_en": "origin_note", "origin_note_uk": "origin_note_uk",
    "technique_en": "technique", "technique_uk": "technique_uk", "material_en": "material", "material_uk": "material_uk",
    "care_en": "care", "care_uk": "care_uk",
}
VARIANT_COLUMNS = {
    "option_label_en": "option_label", "option_label_uk": "option_label_uk", "price_cad": "price_cad",
    "cost_cad": "cost_cad", "weight_g": "weight_g", "length_cm": "length_cm", "width_cm": "width_cm",
    "height_cm": "height_cm", "fibre_content": "fibre_content", "country_of_origin": "country_of_origin",
    "hs_code": "hs_code", "barcode": "barcode",
}
MAKER_COLUMNS = {"maker_name_en": "name", "maker_name_uk": "name_uk", "maker_region_en": "region", "maker_region_uk": "region_uk"}
TRUE = {"yes", "y", "true", "1", "так"}


def _filled(row: dict, mapping: dict) -> dict:
    return {target: row[col].strip() for col, target in mapping.items() if (row.get(col) or "").strip()}


def parse(text: str) -> tuple[list[str], list[dict]]:
    if text.startswith("﻿"):
        text = text[1:]
    reader = csv.DictReader(io.StringIO(text))
    columns = [c.strip() for c in (reader.fieldnames or [])]
    rows = []
    for raw in reader:
        row = {(k or "").strip(): (v if isinstance(v, str) else "") for k, v in raw.items()}
        if not any((v or "").strip() for v in row.values()):
            continue
        rows.append(row)
        if len(rows) > MAX_ROWS:
            raise AdminError(f"The sheet has more than {MAX_ROWS} rows; split it", code="too_many_rows")
    return columns, rows


def run(db: Session, text: str, *, apply: bool) -> dict:
    """Validate (and with apply=True, write) a sheet. The caller commits or rolls back."""
    columns, rows = parse(text)
    missing = sorted(REQUIRED_COLUMNS - set(columns))
    report: dict = {
        "apply": apply, "rows": len(rows), "columns_missing": missing,
        "products": {"create": 0, "update": 0}, "variants": {"create": 0, "update": 0}, "makers": {"create": 0},
        "activated": 0, "errors": 0, "lines": [],
    }
    if missing:
        report["errors"] = 1
        report["lines"].append({"line": 1, "status": "error", "messages": [f"Missing columns: {', '.join(missing)}"]})
        report["applied"] = False
        return report

    savepoint = db.begin_nested()
    seen_products: dict[str, str] = {}
    seen_skus: set[str] = set()
    to_activate: list[tuple[int, Product]] = []
    try:
        for index, row in enumerate(rows, start=2):  # line 1 is the header
            line = {"line": index, "product_slug": row.get("product_slug", "").strip(), "sku": row.get("sku", "").strip().upper(),
                    "status": "ok", "actions": [], "messages": []}
            report["lines"].append(line)
            sku = line["sku"]
            if not sku:
                line["status"] = "error"; line["messages"].append("sku is empty"); continue
            if sku in seen_skus:
                line["status"] = "error"; line["messages"].append(f"SKU {sku} appears twice in the sheet"); continue
            seen_skus.add(sku)
            nested = db.begin_nested()
            try:
                maker_slug = (row.get("maker_slug") or "").strip().lower()
                if maker_slug:
                    maker = db.scalar(select(Maker).where(Maker.slug == maker_slug))
                    if maker is None:
                        data = {"slug": maker_slug, **_filled(row, MAKER_COLUMNS)}
                        if not data.get("name"):
                            raise AdminError(f"Maker {maker_slug} does not exist; add maker_name_en to create it", code="maker")
                        create_maker(db, data)
                        report["makers"]["create"] += 1
                        line["actions"].append(f"create maker {maker_slug}")
                    elif _filled(row, MAKER_COLUMNS):
                        apply_maker(db, maker, _filled(row, MAKER_COLUMNS), creating=False)

                slug = line["product_slug"]
                product_data = _filled(row, PRODUCT_COLUMNS)
                if maker_slug:
                    product_data["maker_slug"] = maker_slug
                product = db.scalar(select(Product).where(Product.slug == slug)) if slug else None
                if product is None:
                    product = create_product(db, {"slug": slug, **product_data})
                    seen_products[slug] = "create"
                    report["products"]["create"] += 1
                    line["actions"].append(f"create product {product.slug}")
                elif slug not in seen_products:
                    apply_product(db, product, product_data, creating=False)
                    seen_products[slug] = "update"
                    report["products"]["update"] += 1
                    line["actions"].append(f"update product {slug}")
                elif product_data:
                    apply_product(db, product, product_data, creating=False)

                variant = db.scalar(select(Variant).where(Variant.sku == sku))
                variant_data = _filled(row, VARIANT_COLUMNS)
                if variant is None:
                    create_variant(db, product, {"sku": sku, **variant_data})
                    report["variants"]["create"] += 1
                    line["actions"].append(f"create variant {sku}")
                else:
                    if variant.product_id and variant.product_id != product.id:
                        raise AdminError(f"SKU {sku} belongs to another product", code="sku_product")
                    variant.product_id = product.id
                    apply_variant(db, variant, product, variant_data, creating=False)
                    report["variants"]["update"] += 1
                    line["actions"].append(f"update variant {sku}")
                if (row.get("on_sale") or "").strip().lower() in TRUE and not product.active:
                    to_activate.append((index, product))
                db.flush()
                nested.commit()
            except (AdminError, ValueError) as exc:
                if nested.is_active:
                    nested.rollback()
                line["status"] = "error"
                line["messages"].append(str(exc))
        done: set[str] = set()
        for index, product in to_activate:
            if product.id in done:
                continue
            done.add(product.id)
            problems = activation_problems(db, product)
            line = next(l for l in report["lines"] if l["line"] == index)
            if problems:
                line["status"] = "error"
                line["messages"].append("Cannot go on sale: " + "; ".join(p["message"] for p in problems))
            else:
                activate(db, product)
                report["activated"] += 1
                line["actions"].append(f"put {product.slug} on sale")
        report["errors"] = sum(1 for l in report["lines"] if l["status"] == "error")
        db.flush()
    finally:
        if not apply or report["errors"]:
            if savepoint.is_active:
                savepoint.rollback()
        elif savepoint.is_active:
            savepoint.commit()
    report["applied"] = bool(apply and not report["errors"])
    return report
