"""Order queue and order page for the owner's /admin screens.

The queue groups orders by the one thing somebody has to do next. The order page carries
everything needed to do it and names that next step as a single action; the storefront
renders it as one button. The actions themselves reuse the pipeline the API already had
(mark-paid, reserve, scan, pack, ship), so the admin cannot take a path the tests do not.
"""
from __future__ import annotations

import json
import os
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..auth import require_operator
from ..deps import get_db
from ..models import (
    ExceptionRecord, Mission, Order, OrderLine, OrderNote, OutboxMessage, Package, Product, ProductImage,
    Reservation, ShipmentRecord, Variant, now_utc,
)
from ..services import mailer, paypal
from ..services.catalog import image_dict
from ..services.inventory import InventoryError, release
from ..services.orders import OrderError, confirm_mission, create_package, open_exception, reserve_order
from ..services.storefront import MAIL_KINDS, MAIL_TOPIC, StorefrontError, cancel_unpaid, mail_key, notify_order

router = APIRouter(prefix="/v1/admin", dependencies=[Depends(require_operator)])

QUEUES = {
    "awaiting_payment": ("AWAITING_PAYMENT",),
    "to_pack": ("PAID", "PICK_PLANNED", "PICKING", "PICK_VERIFIED", "PACKING"),
    "ready_to_ship": ("PACKING", "LABEL_VERIFIED", "READY_FOR_PICKUP"),
    "shipped": ("HANDOFF_COMPLETE",),
    "cancelled": ("CANCELLED",),
}
PAID_OR_LATER = ("PAID", "PICK_PLANNED", "PICKING", "PICK_VERIFIED", "PACKING", "LABEL_VERIFIED",
                 "READY_FOR_PICKUP", "HANDOFF_COMPLETE", "OUT_OF_STOCK")


def _iso(value):
    return value.isoformat() if value else None


def _package(db: Session, order: Order) -> Package | None:
    return db.scalar(select(Package).where(Package.order_id == order.id))


def _queue_of(order: Order, package: Package | None, has_exception: bool) -> str:
    if has_exception or order.state == "OUT_OF_STOCK":
        return "exceptions"
    if order.state == "PACKING":
        return "ready_to_ship" if package and package.weight_g else "to_pack"
    for name, states in QUEUES.items():
        if order.state in states:
            return name
    return "other"


def _order_exception_refs(db: Session, order: Order) -> list[tuple[str, str]]:
    refs = [("ORDER", order.id)]
    if order.order_number:
        refs += [("ORDER", order.order_number), ("ORDER_NUMBER", order.order_number)]
    refs += [("MISSION", mid) for mid in db.scalars(select(Mission.id).where(Mission.order_id == order.id))]
    package = _package(db, order)
    if package:
        refs.append(("PACKAGE", package.id))
    return refs


def order_exceptions(db: Session, order: Order, *, open_only: bool = False) -> list[ExceptionRecord]:
    refs = _order_exception_refs(db, order)
    stmt = select(ExceptionRecord).where(or_(*[
        (ExceptionRecord.reference_type == t) & (ExceptionRecord.reference_id == i) for t, i in refs
    ])).order_by(ExceptionRecord.created_at)
    if open_only:
        stmt = stmt.where(ExceptionRecord.state == "OPEN")
    return list(db.scalars(stmt))


def _open_exception_order_ids(db: Session) -> set[str]:
    rows = list(db.scalars(select(ExceptionRecord).where(ExceptionRecord.state == "OPEN")))
    ids: set[str] = set()
    missions = {}
    packages = {}
    numbers = {}
    for r in rows:
        if r.reference_type == "ORDER":
            ids.add(r.reference_id)
            numbers.setdefault(r.reference_id, None)
        elif r.reference_type == "ORDER_NUMBER":
            numbers.setdefault(r.reference_id, None)
        elif r.reference_type == "MISSION":
            missions[r.reference_id] = None
        elif r.reference_type == "PACKAGE":
            packages[r.reference_id] = None
    if numbers:
        ids |= set(db.scalars(select(Order.id).where(Order.order_number.in_(list(numbers)))))
    if missions:
        ids |= set(db.scalars(select(Mission.order_id).where(Mission.id.in_(list(missions)))))
    if packages:
        ids |= set(db.scalars(select(Package.order_id).where(Package.id.in_(list(packages)))))
    return ids


def _summary(db: Session, order: Order, *, package: Package | None, flagged: bool) -> dict:
    ship_to = json.loads(order.ship_to_json or "{}")
    items = db.scalar(select(func.coalesce(func.sum(OrderLine.qty), 0)).where(OrderLine.order_id == order.id)) or 0
    return {
        "id": order.id, "order_number": order.order_number or order.external_id, "channel": order.channel,
        "state": order.state, "queue": _queue_of(order, package, flagged), "created_at": _iso(order.created_at),
        "paid_at": _iso(order.paid_at), "customer_name": order.customer_name, "customer_email": order.customer_email,
        "city": ship_to.get("city"), "province": ship_to.get("province"), "fulfillment_method": order.fulfillment_method,
        "payment_method": order.payment_method, "total_cad": round(float(order.gross_amount_cad or 0), 2),
        "items": int(items), "demo": bool(order.is_demo), "has_exception": flagged,
    }


@router.get("/orders")
def orders_queue(
    queue: str = Query(default="to_pack", pattern="^(awaiting_payment|to_pack|ready_to_ship|shipped|exceptions|cancelled)$"),
    q: str | None = Query(default=None, max_length=120),
    db: Session = Depends(get_db),
):
    flagged = _open_exception_order_ids(db)
    rows = list(db.scalars(select(Order).where(Order.state.not_in(["DEMO_VOID"])).order_by(Order.created_at.desc()).limit(2000)))
    packages = {p.order_id: p for p in db.scalars(select(Package).where(Package.order_id.in_([o.id for o in rows])))} if rows else {}
    counts = {name: 0 for name in (*QUEUES, "exceptions")}
    items = []
    needle = (q or "").strip().casefold()
    for order in rows:
        summary_queue = _queue_of(order, packages.get(order.id), order.id in flagged)
        if summary_queue in counts:
            counts[summary_queue] += 1
        if needle:
            hay = " ".join(filter(None, [order.order_number, order.external_id, order.customer_name, order.customer_email])).casefold()
            if needle not in hay:
                continue
        elif summary_queue != queue:
            continue
        if len(items) < 200:
            items.append(_summary(db, order, package=packages.get(order.id), flagged=order.id in flagged))
    loose = []
    if queue == "exceptions" and not needle:
        order_refs = set()
        for order_id in flagged:
            o = db.get(Order, order_id)
            if o:
                order_refs |= set(_order_exception_refs(db, o))
        for r in db.scalars(select(ExceptionRecord).where(ExceptionRecord.state == "OPEN").order_by(ExceptionRecord.created_at.desc()).limit(100)):
            if (r.reference_type, r.reference_id) not in order_refs:
                loose.append(_exception_dict(r))
    return {"queue": queue, "counts": counts, "items": items, "other_exceptions": loose}


def _exception_dict(r: ExceptionRecord) -> dict:
    try:
        details = json.loads(r.details)
        summary = details.get("summary") if isinstance(details, dict) else None
    except ValueError:
        details, summary = None, None
    return {
        "id": r.id, "kind": r.kind, "state": r.state, "reference_type": r.reference_type, "reference_id": r.reference_id,
        "summary": summary or r.details[:400], "details": r.details, "created_at": _iso(r.created_at),
        "resolution_note": r.resolution_note, "resolved_by": r.resolved_by, "resolved_at": _iso(r.resolved_at),
    }


def easypost_label_status() -> dict:
    key = bool(os.getenv("EASYPOST_API_KEY", "").strip())
    origin = bool(os.getenv("SHIP_FROM_ADDRESS_JSON", "").strip())
    return {"available": key and origin, "api_key": key, "ship_from": origin}


def next_action(order: Order, package: Package | None, missions: list[Mission]) -> dict:
    method = order.fulfillment_method or "SHIP"
    s = order.state
    if s == "AWAITING_PAYMENT":
        if order.payment_method == "STRIPE":
            return {"kind": "await_card", "secondary": ["cancel"]}
        return {"kind": "mark_paid", "secondary": ["cancel"]}
    if s in {"PAID", "OUT_OF_STOCK"}:
        return {"kind": "reserve", "secondary": ["cancel"]}
    if s in {"PICK_PLANNED", "PICKING"} or (s == "PICK_VERIFIED" and not all(m.state == "CONFIRMED" for m in missions)):
        return {"kind": "scan", "secondary": ["cancel"]}
    if s == "PICK_VERIFIED" or (s == "PACKING" and not (package and package.weight_g)):
        return {"kind": "pack", "secondary": ["cancel"]}
    if s in {"PACKING", "LABEL_VERIFIED", "READY_FOR_PICKUP"}:
        if method == "PICKUP":
            return {"kind": "locker", "secondary": []}
        return {"kind": "ship", "secondary": ["cancel"]}
    return {"kind": "none", "secondary": []}


def _timeline(db: Session, order: Order, package: Package | None, missions: list[Mission], exceptions: list[ExceptionRecord]) -> list[dict]:
    """Order history. `text` is English for scripts; `code` + `params` let the admin page say it in its own language."""
    events: list[dict] = []
    if order.created_at:
        method = order.payment_method or order.channel
        events.append({"at": _iso(order.created_at), "kind": "placed", "text": f"Placed · {method}",
                       "code": "placed", "params": {"method": method}})
    if order.paid_at:
        events.append({"at": _iso(order.paid_at), "kind": "paid", "text": f"Paid · {order.payment_method or ''} {order.payment_ref or ''}".strip(),
                       "code": "paid", "params": {"method": order.payment_method or "", "ref": order.payment_ref or ""}})
    aggregates = [order.id] + ([package.id] if package else [])
    for m in db.scalars(select(OutboxMessage).where(OutboxMessage.aggregate_id.in_(aggregates)).order_by(OutboxMessage.created_at)):
        if m.event_type in {"WEB_ORDER_PLACED", "ORDER_ACCEPTED"}:
            continue
        text = m.event_type.replace("_", " ").lower()
        if m.topic == MAIL_TOPIC:
            mail_kind = m.event_type.removeprefix("ORDER_MAIL_").lower()
            events.append({"at": _iso(m.created_at), "kind": "event", "text": f"email {mail_kind} · {m.state.lower()}",
                           "code": "email", "params": {"mail": mail_kind, "state": m.state}})
            continue
        events.append({"at": _iso(m.created_at), "kind": "event", "text": text, "code": "event", "params": {"event": m.event_type}})
    for m in missions:
        if m.confirmed_at:
            events.append({"at": _iso(m.confirmed_at), "kind": "scan", "text": f"Scanned {m.scanned_barcode}",
                           "code": "scan", "params": {"barcode": m.scanned_barcode or ""}})
    for e in exceptions:
        events.append({"at": _iso(e.created_at), "kind": "exception", "text": f"Problem: {e.kind}", "code": "problem", "params": {"problem": e.kind}})
        if e.resolved_at:
            events.append({"at": _iso(e.resolved_at), "kind": "resolved", "text": f"Resolved {e.kind}: {e.resolution_note or ''}",
                           "code": "resolved", "params": {"problem": e.kind, "note": e.resolution_note or ""}})
    for n in db.scalars(select(OrderNote).where(OrderNote.order_id == order.id)):
        event = {"at": _iso(n.created_at), "kind": "note", "text": n.body, "note_kind": n.kind, "author": n.author, "code": "note", "params": {}}
        if n.kind == "HAND_CHECK":
            hand = re.search(r"no scan: (.+?) ×(\d+)", n.body or "")
            if hand:
                event["code"] = "hand_check"
                event["params"] = {"sku": hand.group(1), "qty": hand.group(2), "author": n.author or ""}
        elif n.kind == "CANCEL":
            event["code"] = "cancel"
        events.append(event)
    events.sort(key=lambda e: e["at"] or "")
    return events


def order_detail(db: Session, order: Order) -> dict:
    package = _package(db, order)
    missions = list(db.scalars(select(Mission).where(Mission.order_id == order.id)))
    exceptions = order_exceptions(db, order)
    shipment = db.scalar(select(ShipmentRecord).where(ShipmentRecord.package_id == package.id)) if package else None
    lines = []
    for line in order.lines:
        v = db.get(Variant, line.variant_id)
        p = db.get(Product, v.product_id) if v and v.product_id else None
        image = db.scalar(select(ProductImage).where(ProductImage.product_id == p.id).order_by(ProductImage.position)) if p else None
        line_missions = [m for m in missions if m.order_line_id == line.id]
        lines.append({
            "id": line.id, "sku": v.sku if v else None, "barcode": v.barcode if v else None, "label": v.option_label if v else None,
            "label_uk": v.option_label_uk if v else None, "title": p.title if p else (v.name if v else "Item"),
            "title_uk": p.title_uk if p else None, "product_id": p.id if p else None, "qty": line.qty,
            "unit_price_cad": round(float(line.unit_price_cad), 2), "line_total_cad": round(line.qty * float(line.unit_price_cad), 2),
            "photo": image_dict(image) if image else (({"src": p.image_url, "srcset": "", "alt": "", "alt_uk": ""}) if p and p.image_url else None),
            "weight_g": v.weight_g if v else None,
            "missions": [{"id": m.id, "state": m.state, "qty": m.qty, "location": m.location_id, "scanned": m.scanned_barcode} for m in line_missions],
            "picked": bool(line_missions) and all(m.state == "CONFIRMED" for m in line_missions),
        })
    open_exc = [e for e in exceptions if e.state == "OPEN"]
    mail = []
    if order.channel == "WEB":
        rows = {m.idempotency_key: m for m in db.scalars(select(OutboxMessage).where(OutboxMessage.topic == MAIL_TOPIC, OutboxMessage.aggregate_id == order.id))}
        for kind in MAIL_KINDS:
            row = rows.get(mail_key(order.id, kind))
            due = (kind == "placed") or (kind == "paid" and order.paid_at) or (kind == "handoff" and order.state == "HANDOFF_COMPLETE") \
                or (kind == "pickup_ready" and (order.fulfillment_method or "") == "PICKUP") \
                or (kind == "cancelled" and order.state == "CANCELLED")
            if row or due:
                mail.append({"kind": kind, "state": row.state if row else "NOT_SENT", "subject": json.loads(row.payload_json or "{}").get("subject") if row else None})
    estimated = sum((l["weight_g"] or 0) * l["qty"] for l in lines)
    return {
        **_summary(db, order, package=package, flagged=bool(open_exc)),
        "customer": {"name": order.customer_name, "email": order.customer_email, "phone": order.customer_phone, "locale": order.locale},
        "ship_to": json.loads(order.ship_to_json or "{}"),
        "note": order.customer_note or "",
        "totals": {"subtotal_cad": order.subtotal_cad, "shipping_cad": order.shipping_cad, "tax_cad": order.tax_cad,
                   "tax_rate": order.tax_rate, "total_cad": round(float(order.gross_amount_cad or 0), 2)},
        "payment": {"method": order.payment_method, "reference": order.payment_ref if not (order.payment_ref or "").startswith("http") else None,
                    "paid_at": _iso(order.paid_at), "hold_expires_at": _iso(order.hold_expires_at),
                    "paypal": {"order_id": order.paypal_order_id, "capture_id": order.paypal_capture_id,
                               "status": order.paypal_status, "tracking_id": order.paypal_tracking_id,
                               "refund_id": order.paypal_refund_id, "sandbox": paypal.sandbox(),
                               "refundable": bool(order.state == "CANCELLED" and order.paypal_capture_id and not order.paypal_refund_id)}
                    if order.payment_method == "PAYPAL" else None},
        "lines": lines,
        "package": {"id": package.id, "state": package.state, "weight_g": package.weight_g} if package else None,
        "estimated_weight_g": estimated or None,
        "shipment": {"provider": shipment.provider, "state": shipment.state, "carrier": shipment.carrier,
                     "tracking_code": shipment.tracking_code, "label_url": shipment.label_url} if shipment else None,
        "exceptions": [_exception_dict(e) for e in exceptions],
        "next": next_action(order, package, missions),
        "timeline": _timeline(db, order, package, missions, exceptions),
        "mail": mail,
        # A local catcher (Mailpit) takes every message and delivers none: "sent" would mislead.
        "mail_captured": _mail_captured(),
        "label": easypost_label_status(),
    }


def _mail_captured() -> bool:
    cfg = mailer.load_config()
    return cfg.enabled and cfg.local_capture


def _order(db: Session, order_id: str) -> Order:
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(404, {"code": "not_found", "message": "Order not found"})
    return order


@router.get("/orders/{order_id}")
def order_get(order_id: str, db: Session = Depends(get_db)):
    return order_detail(db, _order(db, order_id))


class ScanIn(BaseModel):
    barcode: str = Field(min_length=1, max_length=120)


def _pending_scan(db: Session, order: Order) -> tuple[list[Mission], dict[str, Variant]]:
    missions = list(db.scalars(select(Mission).where(Mission.order_id == order.id)))
    if not missions:
        raise HTTPException(409, {"code": "not_reserved", "message": "Reserve the order before scanning",
                                  "message_uk": "Спершу зарезервуйте замовлення"})
    pending = [m for m in missions if m.state != "CONFIRMED"]
    variants = {v.id: v for v in db.scalars(select(Variant).where(Variant.id.in_([m.variant_id for m in pending])))} if pending else {}
    return pending, variants


@router.post("/orders/{order_id}/scan")
def order_scan(order_id: str, inp: ScanIn, db: Session = Depends(get_db)):
    """One scan against the whole order: it confirms the unpicked line whose barcode it is.

    Typing the SKU printed on the order page counts the same as scanning the barcode, so a
    laptop or phone without a scanner can finish the order. A code that belongs to no
    unpicked line is refused with 409 and written to the exception list as WRONG_SKU,
    against the first line still waiting, so the wrong pick is on record. Scanning that
    line's correct barcode afterwards closes it.
    """
    order = _order(db, order_id)
    code = inp.barcode.strip()
    pending, variants = _pending_scan(db, order)
    if not pending:
        return {"ok": True, "state": order.state, "message": "Every line is already scanned", "detail": order_detail(db, order)}
    match = next((m for m in pending if variants.get(m.variant_id) and variants[m.variant_id].barcode == code), None)
    if match is None:
        folded = code.casefold()
        match = next((m for m in pending if variants.get(m.variant_id) and (variants[m.variant_id].sku or "").casefold() == folded), None)
    if match is None:
        confirm_mission(db, pending[0], code)
        db.commit()
        raise HTTPException(409, {"code": "wrong_barcode",
                                  "message": f"{code} is not an item waiting in this order. Put it back; the scan is logged.",
                                  "message_uk": f"{code} — не той товар для цього замовлення. Поверніть його; сканування записано."})
    v = variants[match.variant_id]
    confirm_mission(db, match, v.barcode)
    db.commit()
    return {"ok": True, "state": order.state, "sku": v.sku, "detail": order_detail(db, order)}


@router.post("/orders/{order_id}/lines/{line_id}/confirm")
def order_line_confirm(order_id: str, line_id: str, db: Session = Depends(get_db), actor: str = Depends(require_operator)):
    """Confirm one line by hand, for an item whose barcode label is missing or unreadable.

    It closes every waiting scan on that line and writes a note on the order naming who
    confirmed it, so a hand check is never mistaken for a scan in the history.
    """
    order = _order(db, order_id)
    line = db.get(OrderLine, line_id)
    if not line or line.order_id != order.id:
        raise HTTPException(404, {"code": "not_found", "message": "Line not found", "message_uk": "Рядок не знайдено"})
    pending, variants = _pending_scan(db, order)
    mine = [m for m in pending if m.order_line_id == line.id]
    if not mine:
        return order_detail(db, order)
    v = variants.get(mine[0].variant_id)
    if not v:
        raise HTTPException(409, {"code": "no_variant", "message": "This line has no product to confirm",
                                  "message_uk": "У цього рядка немає товару"})
    for m in mine:
        confirm_mission(db, m, v.barcode)
    db.add(OrderNote(order_id=order.id, kind="HAND_CHECK", author=actor,
                     body=f"Checked by hand, no scan: {v.sku} ×{sum(m.qty for m in mine)} (confirmed by {actor})"))
    db.commit()
    return order_detail(db, order)


class PackIn(BaseModel):
    weight_g: int = Field(gt=0, le=70000)


@router.post("/orders/{order_id}/pack")
def order_pack(order_id: str, inp: PackIn, db: Session = Depends(get_db)):
    order = _order(db, order_id)
    try:
        package = create_package(db, order)
        package.weight_g = inp.weight_g
        db.commit()
    except OrderError as exc:
        db.rollback()
        raise HTTPException(409, {"code": "pack", "message": str(exc)})
    return order_detail(db, order)


class NoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


@router.post("/orders/{order_id}/notes")
def order_note(order_id: str, inp: NoteIn, db: Session = Depends(get_db), actor: str = Depends(require_operator)):
    order = _order(db, order_id)
    db.add(OrderNote(order_id=order.id, kind="NOTE", body=inp.body.strip(), author=actor))
    db.commit()
    return order_detail(db, order)


class CancelIn(BaseModel):
    note: str = Field(min_length=3, max_length=4000)


@router.post("/orders/{order_id}/cancel")
def order_cancel(order_id: str, inp: CancelIn, db: Session = Depends(get_db), actor: str = Depends(require_operator)):
    """Cancel an order that has not left, with the reason written on it.

    Unpaid: holds are released. Paid: the reservations are released as well, and a
    REFUND_DUE problem names the amount, so the refund is not forgotten; resolve it with a
    note once the money is back with the buyer. The buyer gets the "cancelled" email after the
    commit (no reason is quoted in it: the note is for the shop).
    """
    order = _order(db, order_id)
    if order.state in {"HANDOFF_COMPLETE", "CANCELLED"}:
        raise HTTPException(409, {"code": "state", "message": f"This order is {order.state} and cannot be cancelled"})
    package = _package(db, order)
    if package and package.state == "READY_FOR_PICKUP":
        raise HTTPException(409, {"code": "state", "message": "The parcel is in a locker bay; take it out first"})
    try:
        if order.state == "AWAITING_PAYMENT":
            cancel_unpaid(db, order)
        else:
            for r in db.scalars(select(Reservation).join(OrderLine).where(OrderLine.order_id == order.id, Reservation.state.in_(["ACTIVE", "HOLD"]))):
                release(db, variant_id=r.variant_id, location_id=r.location_id, qty=r.qty, reference_id=r.order_line_id)
                r.state = "RELEASED"
            for m in db.scalars(select(Mission).where(Mission.order_id == order.id)):
                if m.state != "CONFIRMED":
                    m.state = "CANCELLED"
            if package:
                package.state = "CANCELLED"
            order.state = "CANCELLED"
            if order.paid_at:
                open_exception(db, kind="REFUND_DUE", reference_type="ORDER", reference_id=order.id, details=json.dumps({
                    "summary": f"Cancelled after payment. Refund CA$ {float(order.gross_amount_cad or 0):.2f} by {order.payment_method}, then resolve this with a note.",
                    "refund_cad": round(float(order.gross_amount_cad or 0), 2), "payment_method": order.payment_method,
                    "payment_ref": order.payment_ref, "order_number": order.order_number,
                }))
        db.add(OrderNote(order_id=order.id, kind="CANCEL", body=inp.note.strip(), author=actor))
        db.commit()
    except (StorefrontError, InventoryError) as exc:
        db.rollback()
        raise HTTPException(409, {"code": "state", "message": str(exc)})
    notify_order(db, order, "cancelled")
    return order_detail(db, order)


@router.post("/orders/{order_id}/label/rates")
def order_label_rates(order_id: str, db: Session = Depends(get_db)):
    """EasyPost rates for this packed parcel, built from the order's ship-to and SHIP_FROM_ADDRESS_JSON."""
    from ..api.shipping import easypost_quote
    from ..schemas import ShipmentQuoteIn

    status = easypost_label_status()
    if not status["available"]:
        raise HTTPException(409, {"code": "not_configured", "message": "Label buying needs EASYPOST_API_KEY and SHIP_FROM_ADDRESS_JSON"})
    order = _order(db, order_id)
    package = _package(db, order)
    if not package or not package.weight_g:
        raise HTTPException(409, {"code": "pack", "message": "Pack and weigh the parcel first"})
    ship_to = json.loads(order.ship_to_json or "{}")
    try:
        origin = json.loads(os.getenv("SHIP_FROM_ADDRESS_JSON", "{}"))
    except ValueError:
        raise HTTPException(409, {"code": "not_configured", "message": "SHIP_FROM_ADDRESS_JSON is not valid JSON"})
    dims = [1.0, 1.0, 1.0]
    for line in order.lines:
        v = db.get(Variant, line.variant_id)
        if v and v.length_cm and v.width_cm and v.height_cm:
            dims = [max(dims[0], v.length_cm), max(dims[1], v.width_cm), dims[2] + v.height_cm * line.qty]
    inp = ShipmentQuoteIn(
        to_address={"name": ship_to.get("name") or order.customer_name, "street1": ship_to.get("street1", ""),
                    "street2": ship_to.get("street2") or None, "city": ship_to.get("city", ""), "state": ship_to.get("province", ""),
                    "zip": ship_to.get("postal_code", ""), "country": ship_to.get("country", "CA"), "email": order.customer_email},
        from_address=origin,
        length_in=round(dims[0] / 2.54, 1), width_in=round(dims[1] / 2.54, 1), height_in=round(max(dims[2], 1.0) / 2.54, 1),
    )
    return {"package_id": package.id, **easypost_quote(package.id, inp, db)}


@router.get("/summary")
def admin_summary(db: Session = Depends(get_db)):
    """Money and counts for the queue header. Gross counts only orders that were paid."""
    since = now_utc().replace(hour=0, minute=0, second=0, microsecond=0)
    paid_today = db.scalar(select(func.coalesce(func.sum(Order.gross_amount_cad), 0)).where(
        Order.state.in_(PAID_OR_LATER), Order.paid_at.is_not(None), Order.paid_at >= since, Order.is_demo.is_(False))) or 0
    demo_paid_today = db.scalar(select(func.coalesce(func.sum(Order.gross_amount_cad), 0)).where(
        Order.state.in_(PAID_OR_LATER), Order.paid_at.is_not(None), Order.paid_at >= since, Order.is_demo.is_(True))) or 0
    return {"paid_today_cad": f"{float(paid_today):.2f}", "demo_paid_today_cad": f"{float(demo_paid_today):.2f}"}


# ------------------------------------------------------------------ locker (read-only overview)

@router.get("/lockers")
def lockers(db: Session = Depends(get_db)):
    """Every bay with its sensors, what is inside, the buyer code window and courier pickups.

    Read-only on purpose: parcels go into a bay from the order page, and doors are driven by
    the edge device. Codes themselves are never listed here, only whether one is live.
    """
    from ..models import Bay, CourierPickup, Device, LockerAccess
    from ..services.locker import pickup_address

    now = now_utc()
    bays = list(db.scalars(select(Bay).order_by(Bay.id)))
    packages = list(db.scalars(select(Package).where(Package.bay_id.is_not(None), Package.state.not_in(["HANDOFF_COMPLETE", "CANCELLED"]))))
    orders = {o.id: o for o in db.scalars(select(Order).where(Order.id.in_([p.order_id for p in packages])))} if packages else {}
    access = list(db.scalars(select(LockerAccess).where(
        LockerAccess.used_at.is_(None), LockerAccess.revoked_at.is_(None), LockerAccess.valid_until > now)))
    pickups = list(db.scalars(select(CourierPickup).where(CourierPickup.state.not_in(["HANDOFF_COMPLETE", "CANCELLED"])).order_by(CourierPickup.window_start)))
    out = []
    for b in bays:
        inside = [p for p in packages if p.bay_id == b.id]
        out.append({
            "id": b.id, "carrier_group": b.carrier_group, "enabled": b.enabled, "weight_g": b.weight_g,
            "inner_gate_closed": b.inner_gate_closed, "outer_door_closed": b.outer_door_closed, "outer_door_locked": b.outer_door_locked,
            "parcels": [{"package_id": p.id, "state": p.state, "order_id": p.order_id,
                         "order_number": orders[p.order_id].order_number if p.order_id in orders else None} for p in inside],
            "customer_codes": [{"order_id": a.order_id, "valid_until": _iso(a.valid_until)} for a in access if a.bay_id == b.id and a.kind == "CUSTOMER"],
            "courier_pickups": [{"id": c.id, "carrier": c.carrier, "state": c.state, "window_start": _iso(c.window_start), "window_end": _iso(c.window_end)}
                                for c in pickups if c.bay_id == b.id],
        })
    devices = [{"id": d.id, "kind": d.kind, "state": d.state, "last_seen_at": _iso(d.last_seen_at)} for d in db.scalars(select(Device).order_by(Device.id))]
    return {"pickup_configured": bool(pickup_address()), "bays": out, "devices": devices}


@router.get("/orders/{order_id}/paypal")
def order_paypal_view(order_id: str, db: Session = Depends(get_db)):
    """PayPal's own record of this order, read live (status, capture, payer country)."""
    order = _order(db, order_id)
    if order.payment_method != "PAYPAL" or not order.paypal_order_id:
        raise HTTPException(404, {"code": "not_paypal", "message": "This order was not paid through PayPal"})
    try:
        return paypal.refresh(db, order)
    except paypal.PayPalError as exc:
        raise HTTPException(502, {"code": exc.code, "message": str(exc)})


class RefundIn(BaseModel):
    note: str | None = Field(default=None, max_length=255)


@router.post("/orders/{order_id}/paypal/refund")
def order_paypal_refund(order_id: str, inp: RefundIn, db: Session = Depends(get_db), actor: str = Depends(require_operator)):
    """Give the money back through PayPal for a cancelled order, and close its REFUND_DUE problem.

    Only a cancelled order is refunded here: an order that is still going out is not
    "half refunded" by a stray click.
    """
    order = _order(db, order_id)
    if order.state != "CANCELLED":
        raise HTTPException(409, {"code": "state", "message": "Cancel the order first, then refund it"})
    try:
        result = paypal.refund(db, order, note=inp.note)
    except paypal.PayPalError as exc:
        db.rollback()
        raise HTTPException(502, {"code": exc.code, "message": str(exc), **({"details": exc.details} if exc.details else {})})
    amount = round(float(order.gross_amount_cad or 0), 2)
    for e in db.scalars(select(ExceptionRecord).where(ExceptionRecord.kind == "REFUND_DUE", ExceptionRecord.reference_id == order.id,
                                                      ExceptionRecord.state == "OPEN")):
        e.state = "RESOLVED"
        e.resolution_note = f"Refunded CA$ {amount:.2f} through PayPal, refund {result.get('id')}"
        e.resolved_by = actor
        e.resolved_at = now_utc()
    db.add(OrderNote(order_id=order.id, kind="NOTE", author=actor,
                     body=f"Refunded CA$ {amount:.2f} through PayPal (refund {result.get('id')}, {result.get('status')})."))
    db.commit()
    return order_detail(db, order)


@router.post("/orders/{order_id}/paypal/tracking")
def order_paypal_tracking(order_id: str, db: Session = Depends(get_db), actor: str = Depends(require_operator)):
    """Send a shipped order's carrier and tracking number to PayPal (when the automatic push failed)."""
    order = _order(db, order_id)
    package = _package(db, order)
    shipment = db.scalar(select(ShipmentRecord).where(ShipmentRecord.package_id == package.id)) if package else None
    if order.state != "HANDOFF_COMPLETE" or not shipment or not shipment.tracking_code:
        raise HTTPException(409, {"code": "state", "message": "Ship the order with a tracking number first"})
    try:
        tracker = paypal.push_tracking(db, order, carrier=shipment.carrier or "Other", tracking_number=shipment.tracking_code)
    except paypal.PayPalError as exc:
        db.rollback()
        raise HTTPException(502, {"code": exc.code, "message": str(exc), **({"details": exc.details} if exc.details else {})})
    for e in db.scalars(select(ExceptionRecord).where(ExceptionRecord.kind == "PAYPAL_TRACKING_FAILED", ExceptionRecord.reference_id == order.id,
                                                      ExceptionRecord.state == "OPEN")):
        e.state = "RESOLVED"
        e.resolution_note = f"Tracking reached PayPal ({tracker})"
        e.resolved_by = actor
        e.resolved_at = now_utc()
    db.add(OrderNote(order_id=order.id, kind="NOTE", author=actor, body=f"Tracking {shipment.tracking_code} sent to PayPal ({tracker})."))
    db.commit()
    return order_detail(db, order)
