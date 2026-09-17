"""Owner catalogue API: makers, products, variants, photos, stock, import, taxonomy.

Every route needs the admin key. The storefront's /admin screens call these from the Next.js
server with ADMIN_API_KEY, which never reaches a browser.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..deps import get_db
from ..models import Maker, Product, ProductImage, Variant
from ..services import catalogue_import, media
from ..services.catalog import ORIGINS, category_rows, collection_rows, ensure_taxonomy, image_dict, setting
from ..services.catalog_admin import (
    ADJUST_REASONS, AdminError, activate, adjust_stock, apply_maker, apply_product, apply_variant, create_maker,
    create_product, create_variant, ledger, maker_admin_dict, next_image_position, product_admin_dict,
    receive_stock, reorder_images, sellable_locations, set_setting, stock_rows, validate_size_chart,
)

router = APIRouter(prefix="/v1/admin", dependencies=[Depends(require_admin)])
media_router = APIRouter()


def _fail(exc: AdminError) -> HTTPException:
    return HTTPException(exc.status, {"code": exc.code, "message": str(exc), **({"details": exc.details} if exc.details else {})})


def _get(db: Session, model, key: str, what: str):
    row = db.get(model, key)
    if row is None:
        raise HTTPException(404, {"code": "not_found", "message": f"{what} not found"})
    return row


class Body(BaseModel):
    model_config = {"extra": "allow"}


# ------------------------------------------------------------------ taxonomy and settings

@router.get("/taxonomy")
def taxonomy(db: Session = Depends(get_db)):
    ensure_taxonomy(db)
    db.commit()
    return {
        "categories": category_rows(db, include_inactive=True),
        "collections": collection_rows(db, include_inactive=True),
        "origins": [{"id": k, **v} for k, v in ORIGINS.items()],
        "locations": sellable_locations(db),
        "adjust_reasons": [{"id": k, "label": v[0], "label_uk": v[1]} for k, v in ADJUST_REASONS.items()],
        "size_chart_default": setting(db, "size_chart_default"),
    }


class SizeChartIn(BaseModel):
    chart: dict | None = None


@router.put("/settings/size-chart-default")
def put_size_chart_default(inp: SizeChartIn, db: Session = Depends(get_db)):
    try:
        chart = validate_size_chart(inp.chart)
    except AdminError as exc:
        raise _fail(exc)
    set_setting(db, "size_chart_default", chart)
    db.commit()
    return {"size_chart_default": chart}


# ------------------------------------------------------------------ makers

@router.get("/makers")
def makers(status: str = Query(default="all", pattern="^(all|active|retired)$"), db: Session = Depends(get_db)):
    stmt = select(Maker).order_by(Maker.position, Maker.name)
    if status != "all":
        stmt = stmt.where(Maker.active.is_(status == "active"))
    return {"items": [maker_admin_dict(db, m) for m in db.scalars(stmt)]}


@router.post("/makers", status_code=201)
def maker_create(inp: Body, db: Session = Depends(get_db)):
    try:
        m = create_maker(db, inp.model_dump())
        db.commit()
    except AdminError as exc:
        db.rollback()
        raise _fail(exc)
    return maker_admin_dict(db, m)


@router.get("/makers/{maker_id}")
def maker_get(maker_id: str, db: Session = Depends(get_db)):
    return maker_admin_dict(db, _get(db, Maker, maker_id, "Maker"))


@router.patch("/makers/{maker_id}")
def maker_patch(maker_id: str, inp: Body, db: Session = Depends(get_db)):
    m = _get(db, Maker, maker_id, "Maker")
    try:
        apply_maker(db, m, inp.model_dump(), creating=False)
        db.commit()
    except AdminError as exc:
        db.rollback()
        raise _fail(exc)
    return maker_admin_dict(db, m)


@router.post("/makers/{maker_id}/{action}")
def maker_retire(maker_id: str, action: str, db: Session = Depends(get_db)):
    if action not in {"retire", "unretire"}:
        raise HTTPException(404, "Unknown action")
    m = _get(db, Maker, maker_id, "Maker")
    m.active = action == "unretire"
    db.commit()
    return maker_admin_dict(db, m)


# ------------------------------------------------------------------ products

@router.get("/products")
def products(
    q: str | None = Query(default=None, max_length=80),
    status: str = Query(default="all", pattern="^(all|active|inactive)$"),
    db: Session = Depends(get_db),
):
    stmt = select(Product).order_by(Product.position, Product.title)
    if status != "all":
        stmt = stmt.where(Product.active.is_(status == "active"))
    rows = list(db.scalars(stmt))
    if q:
        needle = q.strip().casefold()
        sku_hits = set(db.scalars(select(Variant.product_id).where(or_(Variant.sku.ilike(f"%{q.strip()}%"), Variant.barcode == q.strip()))))
        rows = [p for p in rows if p.id in sku_hits or needle in " ".join(filter(None, [p.title, p.title_uk, p.slug])).casefold()]
    return {"items": [product_admin_dict(db, p, full=False) for p in rows], "total": len(rows)}


@router.post("/products", status_code=201)
def product_create(inp: Body, db: Session = Depends(get_db)):
    try:
        ensure_taxonomy(db)
        p = create_product(db, inp.model_dump())
        db.commit()
    except AdminError as exc:
        db.rollback()
        raise _fail(exc)
    return product_admin_dict(db, p)


@router.get("/products/{product_id}")
def product_get(product_id: str, db: Session = Depends(get_db)):
    return product_admin_dict(db, _get(db, Product, product_id, "Product"))


@router.patch("/products/{product_id}")
def product_patch(product_id: str, inp: Body, db: Session = Depends(get_db)):
    p = _get(db, Product, product_id, "Product")
    try:
        apply_product(db, p, inp.model_dump(), creating=False)
        db.commit()
    except AdminError as exc:
        db.rollback()
        raise _fail(exc)
    return product_admin_dict(db, p)


@router.post("/products/{product_id}/activate")
def product_activate(product_id: str, db: Session = Depends(get_db)):
    p = _get(db, Product, product_id, "Product")
    try:
        activate(db, p)
        db.commit()
    except AdminError as exc:
        db.rollback()
        raise _fail(exc)
    return product_admin_dict(db, p)


@router.post("/products/{product_id}/retire")
def product_retire(product_id: str, db: Session = Depends(get_db)):
    p = _get(db, Product, product_id, "Product")
    p.active = False
    db.commit()
    return product_admin_dict(db, p)


# ------------------------------------------------------------------ variants

@router.post("/products/{product_id}/variants", status_code=201)
def variant_create(product_id: str, inp: Body, db: Session = Depends(get_db)):
    p = _get(db, Product, product_id, "Product")
    try:
        create_variant(db, p, inp.model_dump())
        db.commit()
    except AdminError as exc:
        db.rollback()
        raise _fail(exc)
    return product_admin_dict(db, p)


@router.patch("/variants/{variant_id}")
def variant_patch(variant_id: str, inp: Body, db: Session = Depends(get_db)):
    v = _get(db, Variant, variant_id, "Variant")
    p = _get(db, Product, v.product_id, "Product") if v.product_id else None
    if p is None:
        raise HTTPException(409, {"code": "no_product", "message": "This SKU is not attached to a product"})
    try:
        apply_variant(db, v, p, inp.model_dump(), creating=False)
        db.commit()
    except AdminError as exc:
        db.rollback()
        raise _fail(exc)
    return product_admin_dict(db, p)


@router.post("/variants/{variant_id}/{action}")
def variant_retire(variant_id: str, action: str, db: Session = Depends(get_db)):
    if action not in {"retire", "unretire"}:
        raise HTTPException(404, "Unknown action")
    v = _get(db, Variant, variant_id, "Variant")
    v.active = action == "unretire"
    db.commit()
    p = db.get(Product, v.product_id) if v.product_id else None
    return product_admin_dict(db, p) if p else {"id": v.id, "active": v.active}


# ------------------------------------------------------------------ photos

@router.post("/products/{product_id}/images", status_code=201)
async def image_upload(
    product_id: str,
    request: Request,
    file: UploadFile = File(...),
    alt_en: str = Form(default=""),
    alt_uk: str = Form(default=""),
    db: Session = Depends(get_db),
):
    p = _get(db, Product, product_id, "Product")
    try:
        media.check_name(file.filename or "")
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > media.max_upload_bytes() + 64 * 1024:
            # The form overhead is far below 64 KB, so this is the file itself being too big,
            # refused before any of it is read.
            media.check_size(int(declared))
        data = await file.read(media.max_upload_bytes() + 1)
        media.check_size(len(data))
        processed = media.process(data, file.filename or "")
    except media.MediaError as exc:
        status = 413 if exc.code == "too_large" else 415 if exc.code == "type" else 422
        raise HTTPException(status, exc.as_detail())
    image = ProductImage(
        product_id=p.id, position=next_image_position(db, p.id), alt_en=alt_en.strip()[:300], alt_uk=alt_uk.strip()[:300],
        width=processed.width, height=processed.height, widths=",".join(str(w) for w in processed.widths),
        original_name=(file.filename or "")[:200], bytes_in=len(data),
    )
    db.add(image)
    db.flush()
    media.write(p.id, image.id, processed)
    db.commit()
    return image_dict(image)


class ImagePatchIn(BaseModel):
    alt_en: str | None = Field(default=None, max_length=300)
    alt_uk: str | None = Field(default=None, max_length=300)


@router.patch("/images/{image_id}")
def image_patch(image_id: str, inp: ImagePatchIn, db: Session = Depends(get_db)):
    image = _get(db, ProductImage, image_id, "Photo")
    if inp.alt_en is not None:
        image.alt_en = inp.alt_en.strip()
    if inp.alt_uk is not None:
        image.alt_uk = inp.alt_uk.strip()
    db.commit()
    return image_dict(image)


@router.delete("/images/{image_id}")
def image_delete(image_id: str, db: Session = Depends(get_db)):
    image = _get(db, ProductImage, image_id, "Photo")
    product_id = image.product_id
    db.delete(image)
    db.commit()
    media.remove(product_id, image_id)
    return {"ok": True}


class ReorderIn(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=60)


@router.post("/products/{product_id}/images/order")
def image_order(product_id: str, inp: ReorderIn, db: Session = Depends(get_db)):
    p = _get(db, Product, product_id, "Product")
    try:
        reorder_images(db, p, inp.ids)
        db.commit()
    except AdminError as exc:
        db.rollback()
        raise _fail(exc)
    return {"images": [image_dict(i) for i in db.scalars(select(ProductImage).where(ProductImage.product_id == p.id).order_by(ProductImage.position))]}


# ------------------------------------------------------------------ stock

@router.get("/stock")
def stock(q: str | None = Query(default=None, max_length=80), db: Session = Depends(get_db)):
    variants = list(db.scalars(select(Variant).order_by(Variant.sku)))
    products = {p.id: p for p in db.scalars(select(Product))}
    if q:
        needle = q.strip().casefold()
        variants = [v for v in variants if needle in v.sku.casefold() or needle == v.barcode
                    or (v.product_id in products and needle in f"{products[v.product_id].title} {products[v.product_id].title_uk or ''}".casefold())]
    rows = stock_rows(db, variants)
    items = []
    for v in variants:
        p = products.get(v.product_id)
        items.append({
            "variant_id": v.id, "sku": v.sku, "barcode": v.barcode, "label": v.option_label, "label_uk": v.option_label_uk,
            "product_id": p.id if p else None, "product_title": p.title if p else v.name,
            "product_title_uk": p.title_uk if p else None, "product_active": bool(p and p.active), "variant_active": v.active,
            **rows[v.id],
        })
    items.sort(key=lambda i: (i["product_title"] or "", i["sku"]))
    return {"items": items}


class ReceiveIn(BaseModel):
    sku: str = Field(min_length=1, max_length=80)
    qty: int = Field(gt=0, le=100000)
    location_id: str | None = Field(default=None, max_length=80)
    note: str | None = Field(default=None, max_length=1000)


@router.post("/stock/receive")
def stock_receive(inp: ReceiveIn, db: Session = Depends(get_db), actor: str = Depends(require_admin)):
    try:
        event = receive_stock(db, sku=inp.sku, qty=inp.qty, location_id=inp.location_id, note=inp.note, actor=actor)
        db.commit()
    except AdminError as exc:
        db.rollback()
        raise _fail(exc)
    variant = db.get(Variant, event.variant_id)
    return {"ok": True, "sku": variant.sku, "qty": inp.qty, "location": event.to_location_id, **stock_rows(db, [variant])[variant.id]}


class AdjustIn(BaseModel):
    sku: str = Field(min_length=1, max_length=80)
    delta: int
    reason: str = Field(min_length=1, max_length=40)
    location_id: str | None = Field(default=None, max_length=80)
    note: str | None = Field(default=None, max_length=1000)


@router.post("/stock/adjust")
def stock_adjust(inp: AdjustIn, db: Session = Depends(get_db), actor: str = Depends(require_admin)):
    try:
        event = adjust_stock(db, sku=inp.sku, delta=inp.delta, location_id=inp.location_id, reason=inp.reason, note=inp.note, actor=actor)
        db.commit()
    except AdminError as exc:
        db.rollback()
        raise _fail(exc)
    variant = db.get(Variant, event.variant_id)
    return {"ok": True, "sku": variant.sku, "delta": inp.delta, **stock_rows(db, [variant])[variant.id]}


@router.get("/stock/{sku}/ledger")
def stock_ledger(sku: str, db: Session = Depends(get_db)):
    variant = db.scalar(select(Variant).where(Variant.sku == sku.upper()))
    if not variant:
        raise HTTPException(404, {"code": "not_found", "message": "Unknown SKU"})
    return {"sku": variant.sku, "events": ledger(db, variant)}


# ------------------------------------------------------------------ import

@router.post("/import")
async def import_sheet(request: Request, apply: bool = False, db: Session = Depends(get_db)):
    raw = await request.body()
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(413, {"code": "too_large", "message": "The sheet is larger than 5 MB; split it"})
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(400, {"code": "encoding", "message": "Save the sheet as CSV UTF-8"})
    try:
        ensure_taxonomy(db)
        report = catalogue_import.run(db, text, apply=apply)
        if report["applied"]:
            db.commit()
        else:
            db.rollback()
    except AdminError as exc:
        db.rollback()
        raise _fail(exc)
    return report


# ------------------------------------------------------------------ public media

@media_router.get("/media/{path:path}")
def media_file(path: str):
    target = media.resolve(path)
    if target is None:
        raise HTTPException(404, "Not found")
    return FileResponse(target, media_type="image/webp", headers={"Cache-Control": "public, max-age=31536000, immutable"})
