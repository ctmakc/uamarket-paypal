"""Storefront orders: the public web channel into the same order pipeline Shopify uses.

Honesty rules baked in here:
- a web order is created as AWAITING_PAYMENT and becomes PAID only when money is
  confirmed (a PayPal capture or webhook, a Stripe webhook, or an operator marking an
  e-Transfer received);
- prices always come from the database, never from the browser;
- totals (shipping, tax) come from configuration the owner sets, and when tax is not
  configured for a province no tax line is invented;
- the shop never claims a live quantity; it refuses lines it cannot currently cover.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Maker, Order, OrderLine, OutboxMessage, Package, Product, ShipmentRecord, Variant, WebhookEvent, now_utc
from . import locker, mailer, paypal
from .catalog import _availability_map, images_map, media_url
from .inventory import InventoryError
from .orders import hold_stock, holds_cover_order, open_exception, release_holds, reserve_order
from .outbox import acknowledge, enqueue
from . import tax as taxes
from .routable import routable_or_none

log = logging.getLogger("uamarket.storefront")

ALPHABET = "23456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford-ish: no 0/O/1/I/L
MAX_LINE_QTY = 20
MAX_LINES = 30
PROVINCES = {"AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC", "SK", "YT"}

CUSTOMER_STATES = {
    "AWAITING_PAYMENT": ("awaiting_payment", "Awaiting payment", "Очікує оплати"),
    "PAID": ("paid", "Paid, preparing", "Оплачено, готуємо"),
    # Paying reserves the goods at once, so a freshly paid order is already PICK_PLANNED.
    # Until someone has picked it, the buyer is told what is true: paid, being prepared.
    "PICK_PLANNED": ("paid", "Paid, preparing", "Оплачено, готуємо"),
    "PICKING": ("paid", "Paid, preparing", "Оплачено, готуємо"),
    "PICK_VERIFIED": ("packing", "Being packed", "Пакуємо"),
    "PACKING": ("packing", "Being packed", "Пакуємо"),
    "LABEL_VERIFIED": ("packing", "Being packed", "Пакуємо"),
    "READY_FOR_PICKUP": ("ready", "Ready for the courier", "Готово до відправки"),
    "HANDOFF_COMPLETE": ("shipped", "Shipped", "Відправлено"),
    "OUT_OF_STOCK": ("delayed", "Delayed: an item is unavailable, we will contact you", "Затримка: товару немає, ми напишемо вам"),
    "CANCELLED": ("cancelled", "Cancelled", "Скасовано"),
}

# The same warehouse states, read by someone who is collecting the parcel themselves. A
# buyer waiting at a locker is never told their order went to a courier.
PICKUP_STATES = {
    "READY_FOR_PICKUP": ("ready", "In the locker, waiting for you", "У локері, чекає на вас"),
    "HANDOFF_COMPLETE": ("collected", "Collected", "Забрано"),
}


class StorefrontError(RuntimeError):
    def __init__(self, message: str, *, code: str = "invalid", details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


# --------------------------------------------------------------------------- config

def _money(value: str | None, default: float) -> float:
    try:
        return round(float(value), 2) if value not in (None, "") else default
    except ValueError:
        return default


def tax_rates() -> dict[str, float]:
    """Combined rate per province where a tax line applies (see app/services/tax.py)."""
    return {p: round(sum(c["rate"] for c in taxes.components(p)), 5) for p in taxes.configured_provinces()}


# Provinces the shop does not ship to. Unset means Quebec, because the storefront has no
# French version; "none" ships everywhere in PROVINCES.
DEFAULT_EXCLUDED_PROVINCES = ("QC",)

EXCLUDED_REASON = {
    "QC": ("We do not ship to Quebec yet, because the shop is not available in French.",
           "Поки що ми не доставляємо в Квебек, бо крамниця не має французької версії."),
}
EXCLUDED_REASON_DEFAULT = ("We do not ship to this province yet.", "Поки що ми не доставляємо в цю провінцію.")


def excluded_provinces() -> list[str]:
    raw = os.getenv("SHOP_SHIP_EXCLUDE_PROVINCES")
    if raw is None or not raw.strip():
        return list(DEFAULT_EXCLUDED_PROVINCES)
    if raw.strip().lower() == "none":
        return []
    return sorted({p.strip().upper() for p in raw.split(",") if p.strip().upper() in PROVINCES})


def excluded_reason(province: str) -> tuple[str, str]:
    return EXCLUDED_REASON.get(province, EXCLUDED_REASON_DEFAULT)


def business_identity() -> dict:
    """Who sells: the block the terms, privacy and contact pages print. None = not published yet."""
    def env(name: str) -> str | None:
        return (os.getenv(name) or "").strip() or None

    return {
        "legal_name": env("SHOP_LEGAL_NAME"),
        "legal_name_uk": env("SHOP_LEGAL_NAME_UK"),
        "address": env("SHOP_BUSINESS_ADDRESS"),
        "contact_email": contact_email(),
        "privacy_email": routable_or_none(os.getenv("SHOP_PRIVACY_EMAIL")) or None,
        "gst_number": taxes.gst_number(),
    }


def processors() -> list[dict]:
    """Outside services that handle buyer data on this deployment, read from what is configured.

    kind is email | payments | shipping | hosting; name is None while the service is in use
    and its provider has not been named (hosting only).
    """
    out = []
    mail = mailer.load_config()
    if mail.enabled and not mail.local_capture:
        name = (os.getenv("MAIL_PROVIDER_NAME") or "").strip() or mail.host
        out.append({"kind": "email", "name": name, "data": "email address, name, order contents"})
    if paypal.configured():
        out.append({"kind": "payments", "name": "PayPal" + (" (sandbox)" if paypal.sandbox() else ""),
                    "data": "email address, order lines and totals, delivery address"})
    if stripe_enabled():
        out.append({"kind": "payments", "name": "Stripe", "data": "email address, card payment"})
    if (os.getenv("EASYPOST_API_KEY") or "").strip():
        out.append({"kind": "shipping", "name": "EasyPost", "data": "name, delivery address, phone"})
    hosting = (os.getenv("SHOP_HOSTING_PROVIDER") or "").strip() or None
    out.append({"kind": "hosting", "name": hosting, "data": "everything the shop stores"})
    return out


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def catalogue_live() -> bool:
    """The assortment is real only after the owner says so. Until then orders are demos."""
    return (os.getenv("SHOP_CATALOGUE_STATUS") or "").strip().lower() == "live"


def payment_provider() -> str:
    """`stripe` (default) or `fake`, the local test provider that moves no money."""
    raw = (os.getenv("PAYMENT_PROVIDER") or "").strip().lower()
    return "fake" if raw == "fake" else "stripe"


class ConfigurationError(RuntimeError):
    pass


def check_payment_configuration() -> None:
    """Refuse to start a shop that could show a test card page to the public.

    The fake provider completes a payment with one click and no money. It is for a laptop
    and a docker compose run, and a deployment that is indexable or sells the real
    catalogue must never carry it.
    """
    if paypal.configured() and paypal.sandbox() and catalogue_live():
        # The sandbox moves pretend money: a real assortment must never be "sold" through it.
        raise ConfigurationError("PAYPAL_ENV=sandbox is refused while SHOP_CATALOGUE_STATUS=live")
    if payment_provider() != "fake":
        return
    if _truthy(os.getenv("WEB_INDEXABLE")):
        raise ConfigurationError("PAYMENT_PROVIDER=fake is refused while WEB_INDEXABLE=true")
    if catalogue_live():
        raise ConfigurationError("PAYMENT_PROVIDER=fake is refused while SHOP_CATALOGUE_STATUS=live")


def fake_payments_enabled() -> bool:
    if payment_provider() != "fake":
        return False
    try:
        check_payment_configuration()
    except ConfigurationError:
        return False
    return True


def etransfer_email() -> str | None:
    return routable_or_none(os.getenv("ETRANSFER_EMAIL"))


def contact_email() -> str | None:
    return routable_or_none(os.getenv("SHOP_CONTACT_EMAIL"))


def payment_methods() -> list[str]:
    """Methods a buyer can actually complete. An empty list means the shop takes no orders.

    Card is offered with the fake provider, or with Stripe when both the secret key and the
    webhook secret are set: without the webhook secret a paid session could never mark the
    order paid. e-Transfer needs a routable recipient address.
    """
    methods = []
    if paypal.configured():
        methods.append("PAYPAL")
    if fake_payments_enabled() or stripe_enabled():
        methods.append("STRIPE")
    if etransfer_email():
        methods.append("ETRANSFER")
    return methods


def order_hold_minutes() -> int:
    """How long placement holds stock for an unpaid order (software default 60)."""
    try:
        value = int((os.getenv("ORDER_HOLD_MINUTES") or "").strip())
    except ValueError:
        return 60
    return max(5, min(value, 24 * 60))


def storefront_config() -> dict:
    methods = payment_methods()
    return {
        "currency": "CAD",
        "locales": ["en", "uk"],
        "shipping": {
            "flat_cad": _money(os.getenv("SHIPPING_FLAT_CAD"), 12.00),
            "free_over_cad": _money(os.getenv("SHIPPING_FREE_OVER_CAD"), 150.00),
            "countries": ["CA"],
            "excluded_provinces": excluded_provinces(),
            "excluded_reasons": {p: {"en": excluded_reason(p)[0], "uk": excluded_reason(p)[1]} for p in excluded_provinces()},
        },
        # Pickup is offered only when the owner has said where the locker is; the address,
        # the hours and the validity of a bay code all come from app/services/locker.py.
        "pickup": locker.pickup_config(),
        "tax": taxes.config(),
        "business": business_identity(),
        "processors": processors(),
        "payment_methods": methods,
        # False while no method above can be completed: the checkout shows that the shop
        # is not taking orders yet, and the order endpoint refuses.
        "taking_orders": bool(methods),
        # Minutes placing an order sets its stock aside while the buyer pays.
        "hold_minutes": order_hold_minutes(),
        # True when card payments go to the local fake provider: no money moves.
        "payment_test_mode": "STRIPE" in methods and fake_payments_enabled(),
        # PayPal JS SDK v6 settings (browser-safe client id, sandbox or live), or None.
        "paypal": paypal.public_config(),
        "catalogue": "live" if catalogue_live() else "placeholder",
        "etransfer_email": etransfer_email(),
        "contact_email": contact_email(),
        # What the storefront may promise: an order confirmation reaches the customer by
        # email only while SMTP is configured. The pages read this and change their copy.
        "notifications": notifications_config(),
    }


# --------------------------------------------------------------------------- totals

def compute_totals(subtotal: float, *, fulfillment_method: str, province: str | None) -> dict:
    """What this basket costs by the method the shop will actually accept.

    Pickup carries no shipping line, and that is true only where pickup is a method the
    shop sells. A bag that asks for pickup in a shop with no locker address is priced as
    what it will have to become — a parcel — so the quote never shows a total the checkout
    will refuse to honour. Tax is a list of named lines (GST, HST, QST, PST) from
    app/services/tax.py; `tax_rate` is their sum.
    """
    cfg = storefront_config()
    if fulfillment_method == "PICKUP" and cfg["pickup"]["enabled"]:
        shipping = 0.0
        tax_province = cfg["pickup"]["province"]
    else:
        shipping = 0.0 if subtotal >= cfg["shipping"]["free_over_cad"] else cfg["shipping"]["flat_cad"]
        tax_province = (province or "").upper()
    taxable = round(subtotal + shipping, 2)
    lines = taxes.tax_lines(taxable, tax_province)
    tax = round(sum(line["amount_cad"] for line in lines), 2)
    rate = round(sum(line["rate"] for line in lines), 5) if lines else None
    return {
        "subtotal_cad": round(subtotal, 2),
        "shipping_cad": round(shipping, 2),
        "tax_cad": tax,
        "tax_rate": rate,
        "tax_lines": lines,
        "tax_province": tax_province if lines else None,
        "total_cad": round(subtotal + shipping + tax, 2),
    }


# --------------------------------------------------------------------------- orders

def new_order_number(db: Session) -> str:
    stamp = datetime.now(timezone.utc).strftime("%y%m%d")
    for _ in range(20):
        tail = "".join(secrets.choice(ALPHABET) for _ in range(4))
        candidate = f"UA-{stamp}-{tail}"
        if not db.scalar(select(Order).where(Order.order_number == candidate)):
            return candidate
    raise StorefrontError("Could not allocate an order number", code="internal")


def new_access_token() -> str:
    """The opaque key to one order's page: in the order email link and in the buyer's cookie."""
    return secrets.token_urlsafe(24)


def _validate_customer(payload: dict) -> dict:
    email = (payload.get("email") or "").strip().lower()
    name = (payload.get("name") or "").strip()
    if "@" not in email or "." not in email.split("@")[-1] or len(email) > 200:
        raise StorefrontError("A valid email is required", code="email")
    if len(name) < 2 or len(name) > 200:
        raise StorefrontError("Name is required", code="name")
    method = (payload.get("fulfillment_method") or "").upper()
    if method not in {"SHIP", "PICKUP"}:
        raise StorefrontError("Choose shipping or pickup", code="fulfillment_method")
    cfg = storefront_config()
    if method == "PICKUP" and not cfg["pickup"]["enabled"]:
        raise StorefrontError("Pickup is not available", code="fulfillment_method")
    ship_to = {}
    if method == "SHIP":
        raw = payload.get("ship_to") or {}
        ship_to = {
            "name": (raw.get("name") or name).strip(),
            "street1": (raw.get("street1") or "").strip(),
            "street2": (raw.get("street2") or "").strip(),
            "city": (raw.get("city") or "").strip(),
            "province": (raw.get("province") or "").strip().upper(),
            "postal_code": (raw.get("postal_code") or "").strip().upper().replace(" ", ""),
            "country": (raw.get("country") or "CA").strip().upper(),
        }
        missing = [k for k in ("street1", "city", "province", "postal_code") if not ship_to[k]]
        if missing:
            raise StorefrontError("Shipping address is incomplete", code="ship_to", details={"missing": missing})
        if ship_to["country"] not in cfg["shipping"]["countries"]:
            raise StorefrontError("We ship within Canada only", code="ship_to")
        if ship_to["province"] not in PROVINCES:
            raise StorefrontError("Unknown province", code="ship_to")
        if ship_to["province"] in excluded_provinces():
            en, uk = excluded_reason(ship_to["province"])
            raise StorefrontError(en, code="province_excluded", details={"province": ship_to["province"], "message_uk": uk})
        pc = ship_to["postal_code"]
        if len(pc) != 6 or not (pc[0].isalpha() and pc[1].isdigit() and pc[2].isalpha() and pc[3].isdigit() and pc[4].isalpha() and pc[5].isdigit()):
            raise StorefrontError("Postal code must look like K1A 0B1", code="ship_to")
        ship_to["postal_code"] = f"{pc[:3]} {pc[3:]}"
    pm = (payload.get("payment_method") or "").upper() or None
    allowed = payment_methods()
    if not allowed:
        raise StorefrontError("The shop is not taking orders yet", code="not_taking_orders")
    if pm is None:
        pm = allowed[0]
    if pm not in allowed:
        raise StorefrontError("Payment method not available", code="payment_method", details={"allowed": allowed})
    locale = (payload.get("locale") or "en").lower()
    if locale not in {"en", "uk"}:
        locale = "en"
    return {
        "email": email,
        "name": name,
        "phone": (payload.get("phone") or "").strip()[:60] or None,
        "fulfillment_method": method,
        "ship_to": ship_to,
        "payment_method": pm,
        "locale": locale,
        "note": (payload.get("note") or "").strip()[:1000],
    }


def create_web_order(db: Session, payload: dict) -> tuple[Order, bool]:
    """Create an AWAITING_PAYMENT order for the WEB channel. Idempotent on payload['idempotency_key']."""
    key = (payload.get("idempotency_key") or "").strip()
    if not key or len(key) > 120:
        raise StorefrontError("idempotency_key is required", code="idempotency_key")
    prior = db.scalar(select(WebhookEvent).where(WebhookEvent.source == "web", WebhookEvent.external_event_id == key))
    if prior:
        order = db.scalar(select(Order).where(Order.channel == "WEB", Order.external_id == key))
        if not order:
            raise StorefrontError("Order key already used", code="idempotency_key")
        return order, True

    customer = _validate_customer(payload)
    raw_lines = payload.get("lines") or []
    if not raw_lines:
        raise StorefrontError("The bag is empty", code="lines")
    if len(raw_lines) > MAX_LINES:
        raise StorefrontError("Too many lines", code="lines")

    # merge duplicates, validate quantities
    wanted: dict[str, int] = {}
    for line in raw_lines:
        sku = str(line.get("sku") or "").strip()
        try:
            qty = int(line.get("qty"))
        except (TypeError, ValueError):
            raise StorefrontError("Quantity must be a whole number", code="lines")
        if not sku or qty <= 0 or qty > MAX_LINE_QTY:
            raise StorefrontError("Quantity must be between 1 and 20", code="lines", details={"sku": sku})
        wanted[sku] = wanted.get(sku, 0) + qty

    variants = {v.sku: v for v in db.scalars(select(Variant).where(Variant.sku.in_(list(wanted.keys()))))}
    unknown = [sku for sku in wanted if sku not in variants or not variants[sku].active]
    if unknown:
        raise StorefrontError("Some items are no longer sold", code="unknown_sku", details={"skus": unknown})
    products = {p.id: p for p in db.scalars(select(Product).where(Product.id.in_([v.product_id for v in variants.values() if v.product_id])))}
    hidden = [sku for sku, v in variants.items() if v.product_id and (v.product_id not in products or not products[v.product_id].active)]
    if hidden:
        raise StorefrontError("Some items are no longer sold", code="unknown_sku", details={"skus": hidden})
    availability = _availability_map(db, [v.id for v in variants.values()])
    short = [sku for sku, qty in wanted.items() if availability[variants[sku].id].qty < qty]
    if short:
        raise StorefrontError("Not enough stock for some items", code="out_of_stock", details={
            "skus": short,
            "lines": [line_status(qty=wanted[sku], available=availability[variants[sku].id].qty) | {"sku": sku} for sku in short],
        })

    subtotal = 0.0
    order = Order(channel="WEB", external_id=key, state="AWAITING_PAYMENT")
    for sku, qty in wanted.items():
        v = variants[sku]
        price = round(float(v.price_cad), 2)
        order.lines.append(OrderLine(variant_id=v.id, qty=qty, unit_price_cad=price))
        subtotal += qty * price
    totals = compute_totals(round(subtotal, 2), fulfillment_method=customer["fulfillment_method"],
                            province=customer["ship_to"].get("province") if customer["ship_to"] else None)
    order.order_number = new_order_number(db)
    order.customer_email = customer["email"]
    order.customer_name = customer["name"]
    order.customer_phone = customer["phone"]
    order.locale = customer["locale"]
    order.fulfillment_method = customer["fulfillment_method"]
    order.ship_to_json = json.dumps(customer["ship_to"], ensure_ascii=False)
    order.subtotal_cad = totals["subtotal_cad"]
    order.shipping_cad = totals["shipping_cad"]
    order.tax_cad = totals["tax_cad"]
    order.tax_rate = totals["tax_rate"]
    order.tax_lines_json = json.dumps(totals["tax_lines"], ensure_ascii=False)
    order.access_token = new_access_token()
    order.gross_amount_cad = totals["total_cad"]
    order.payment_method = customer["payment_method"]
    order.customer_note = customer["note"]
    order.is_demo = not catalogue_live()
    db.add(order)
    db.add(WebhookEvent(source="web", external_event_id=key,
                        payload_hash=hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()))
    db.flush()
    try:
        hold_stock(db, order, until=now_utc() + timedelta(minutes=order_hold_minutes()))
    except InventoryError:
        # Another order took the last units between the availability read and the hold.
        raise StorefrontError("Not enough stock for some items", code="out_of_stock", details={"skus": list(wanted)})
    freeze_placement(order)
    enqueue(
        db, topic="commerce/orders", event_type="WEB_ORDER_PLACED", aggregate_type="ORDER", aggregate_id=order.id,
        payload={"order_id": order.id, "order_number": order.order_number, "total_cad": order.gross_amount_cad,
                 "payment_method": order.payment_method},
        idempotency_key=f"web-order-placed:{order.id}",
    )
    return order, False


PAID_OUT_OF_STOCK = "PAID_OUT_OF_STOCK"


def mark_paid(db: Session, order: Order, *, reference: str | None = None, method: str | None = None) -> Order:
    """Record that the money arrived, and reserve the goods in the same transaction.

    The reservation turns the placement hold into the order's own stock. When the hold had
    lapsed and the stock has gone since, the order is paid and cannot be filled: it goes to
    OUT_OF_STOCK with an operator exception that names the refund to make.
    """
    if order.paid_at is not None:
        return order
    if order.state != "AWAITING_PAYMENT":
        raise StorefrontError(f"Order is {order.state}, not awaiting payment", code="state")
    order.state = "PAID"
    order.paid_at = now_utc()
    if reference:
        order.payment_ref = reference
    if method:
        order.payment_method = method
    enqueue(
        db, topic="commerce/orders", event_type="ORDER_ACCEPTED", aggregate_type="ORDER", aggregate_id=order.id,
        payload={"order_id": order.id, "channel": order.channel, "external_id": order.external_id, "order_number": order.order_number},
        idempotency_key=f"order-accepted:{order.id}",
    )
    db.flush()
    try:
        reserve_order(db, order)
    except InventoryError as exc:
        open_exception(
            db, kind=PAID_OUT_OF_STOCK, reference_type="ORDER", reference_id=order.id,
            details=json.dumps({
                "order_number": order.order_number,
                "summary": "Paid, and the stock is gone. Restock and reserve again, or refund the buyer.",
                "refund_cad": order.gross_amount_cad,
                "payment_method": order.payment_method,
                "payment_ref": order.payment_ref,
                "reason": str(exc),
            }, ensure_ascii=False),
        )
    return order


def cancel_unpaid(db: Session, order: Order) -> Order:
    if order.state != "AWAITING_PAYMENT":
        raise StorefrontError(f"Only unpaid orders can be cancelled here (order is {order.state})", code="state")
    order.state = "CANCELLED"
    release_holds(db, order)
    return order


def release_expired_holds(db: Session, *, now: datetime | None = None, limit: int = 200) -> int:
    """Release the stock of unpaid orders whose placement hold ran out. Returns orders touched.

    The order stays open: an e-Transfer can still arrive, and a card buyer can start a new
    payment, which takes a fresh hold when the stock is still there.
    """
    moment = now or now_utc()
    rows = list(db.scalars(
        select(Order)
        .where(Order.state == "AWAITING_PAYMENT", Order.hold_expires_at.is_not(None), Order.hold_expires_at <= moment)
        .order_by(Order.hold_expires_at)
        .limit(limit)
    ))
    for order in rows:
        release_holds(db, order)
    return len(rows)


def freeze_placement(order: Order) -> None:
    """Keep what the buyer is told at placement, for the "order received" email."""
    try:
        prior = json.loads(order.placement_json or "{}")
    except ValueError:
        prior = {}
    prior["payment"] = payment_instructions(order)
    order.placement_json = json.dumps(prior, ensure_ascii=False, default=str)


def terms_version() -> str | None:
    """The version of the terms of sale in force (SHOP_TERMS_VERSION, e.g. a date). None = unset."""
    return (os.getenv("SHOP_TERMS_VERSION") or "").strip()[:40] or None


def record_terms_acceptance(order: Order) -> None:
    """Keep, with the order, that the buyer accepted the terms, when, and which version."""
    try:
        prior = json.loads(order.placement_json or "{}")
    except ValueError:
        prior = {}
    prior["terms"] = {"accepted": True, "at": now_utc().isoformat(), "version": terms_version()}
    order.placement_json = json.dumps(prior, ensure_ascii=False, default=str)


def line_status(*, qty: int, available: int) -> dict:
    """ok, reduce or sold_out for one line, with the most the shop can send (never above 20)."""
    cap = max(0, min(int(available), MAX_LINE_QTY))
    if cap <= 0:
        return {"status": "sold_out", "max_qty": 0}
    if qty > cap:
        return {"status": "reduce", "max_qty": cap}
    return {"status": "ok", "max_qty": qty}


def quote(db: Session, *, lines: list[dict], fulfillment_method: str, province: str | None) -> dict:
    """Totals and per-line availability for the bag. Prices are re-read from the database.

    Each line also carries what the bag prints about it in both languages (title, variant
    label, maker, slug, photo), so a bag that stores only SKUs renders in the reader's
    language and follows the catalogue when the owner edits a name.
    """
    wanted: dict[str, int] = {}
    for line in lines:
        wanted[line["sku"]] = wanted.get(line["sku"], 0) + int(line["qty"])
    variants = {v.sku: v for v in db.scalars(select(Variant).where(Variant.sku.in_(list(wanted)), Variant.active.is_(True)))} if wanted else {}
    products = {p.id: p for p in db.scalars(select(Product).where(Product.id.in_([v.product_id for v in variants.values() if v.product_id])))} if variants else {}
    sellable = {sku: v for sku, v in variants.items() if not v.product_id or (v.product_id in products and products[v.product_id].active)}
    availability = _availability_map(db, [v.id for v in sellable.values()])
    makers = {m.id: m for m in db.scalars(select(Maker).where(Maker.id.in_([p.maker_id for p in products.values() if p.maker_id])))} if products else {}
    photos = images_map(db, list(products)) if products else {}
    subtotal = 0.0
    priced = []
    for sku, qty in wanted.items():
        v = sellable.get(sku)
        if v is None:
            priced.append({"sku": sku, "qty": qty, "unit_price_cad": None, "status": "sold_out", "max_qty": 0})
            continue
        state = line_status(qty=qty, available=availability[v.id].qty)
        price = round(float(v.price_cad), 2)
        counted = min(qty, state["max_qty"])
        subtotal += counted * price
        product = products.get(v.product_id) if v.product_id else None
        maker = makers.get(product.maker_id) if product and product.maker_id else None
        pics = photos.get(product.id, []) if product else []
        priced.append({
            "sku": sku, "qty": qty, "unit_price_cad": price, **state,
            "slug": product.slug if product else None,
            "title": product.title if product else v.name,
            "title_uk": product.title_uk if product else None,
            "label": v.option_label or None,
            "label_uk": v.option_label_uk or None,
            "maker": maker.name if maker else None,
            "maker_uk": maker.name_uk if maker else None,
            "origin": product.origin if product else None,
            "image_url": (media_url(pics[0], 480) if pics else (product.image_url if product else None)),
        })
    method = "PICKUP" if (fulfillment_method or "SHIP").upper() == "PICKUP" else "SHIP"
    totals = compute_totals(round(subtotal, 2), fulfillment_method=method, province=province)
    prov = (province or "").strip().upper()
    blocked = None
    if method == "SHIP" and prov in excluded_provinces():
        en, uk = excluded_reason(prov)
        blocked = {"province": prov, "message": en, "message_uk": uk}
    return {"lines": priced, **totals, "ship_blocked": blocked}


def payment_instructions(order: Order) -> dict:
    cfg = storefront_config()
    if order.state != "AWAITING_PAYMENT":
        out = {"method": order.payment_method, "due": False, "demo": bool(order.is_demo)}
        if order.payment_method == "PAYPAL" and order.paypal_capture_id:
            out["paypal"] = {"order_id": order.paypal_order_id, "capture_id": order.paypal_capture_id,
                             "status": order.paypal_status, "sandbox": paypal.sandbox()}
        return out
    checkout_url = order.payment_ref if (order.payment_ref or "").startswith("http") else None
    test_session = (order.checkout_session_id or "").startswith(FAKE_SESSION_PREFIX)
    if order.payment_method == "PAYPAL" and (not order.is_demo or paypal.sandbox()):
        # PayPal sandbox moves no real money, so a demonstration order may be paid through it
        # end to end; a live PayPal account never sees a demo order.
        return {
            "method": "PAYPAL", "due": True, "demo": bool(order.is_demo), "amount_cad": order.gross_amount_cad,
            "paypal": {"order_id": order.paypal_order_id, "status": order.paypal_status, "sandbox": paypal.sandbox()},
            "test_mode": paypal.sandbox(),
        }
    if order.is_demo:
        # Demonstration goods: no recipient, no real card page. The local test card page
        # stays, because it moves no money and is how the purchase path is exercised.
        return {
            "method": order.payment_method, "due": True, "demo": True, "amount_cad": order.gross_amount_cad,
            "checkout_url": checkout_url if (order.payment_method == "STRIPE" and test_session) else None,
            "test_mode": test_session,
        }
    if order.payment_method == "ETRANSFER":
        return {
            "method": "ETRANSFER",
            "due": True,
            "amount_cad": order.gross_amount_cad,
            "recipient_email": cfg["etransfer_email"],
            "message": order.order_number,
        }
    if order.payment_method == "STRIPE":
        return {"method": "STRIPE", "due": True, "amount_cad": order.gross_amount_cad, "checkout_url": checkout_url, "test_mode": test_session}
    return {"method": "INVOICE", "due": True, "amount_cad": order.gross_amount_cad, "contact_email": cfg["contact_email"]}


# --------------------------------------------------------------------------- pickup
#
# What the buyer of a pickup order is allowed to be told, and when. The rule the whole
# block obeys: a code is printed only when a live credential exists, and while none exists
# the page says what has to happen first. Nothing here ever implies a code the shop has not
# minted, and nothing here prints an address the owner has not configured.

PICKUP_COPY = {
    "preparing_mail": (
        "The one-time code and the address arrive by email when your parcel is in the locker, "
        "and this page shows them as well.",
        "Одноразовий код і адресу надішлемо електронною поштою, щойно посилка буде в локері. "
        "Вони також з'являться на цій сторінці.",
    ),
    "preparing_nomail": (
        "This page shows the one-time code and the address when your parcel is in the locker.",
        "Ця сторінка покаже одноразовий код і адресу, щойно посилка буде в локері.",
    ),
    "ready": (
        "The code below opens the bay once.",
        "Код нижче відкриває комірку один раз.",
    ),
    "opened": (
        "The bay was opened with this code, and the code is spent.",
        "Комірку відкрито цим кодом, і код уже використано.",
    ),
    "withdrawn": (
        "The code was withdrawn. Write to the shop about this order.",
        "Код відкликано. Напишіть у крамницю щодо цього замовлення.",
    ),
    "expired": (
        "The code has passed its last hour. Write to the shop and a new one is issued.",
        "Термін дії коду минув. Напишіть у крамницю — вам видадуть новий.",
    ),
    "collected": (
        "The parcel has left the locker.",
        "Посилку забрано з локера.",
    ),
    "no_address": (
        "The pickup address is not published yet. The shop writes to you about this order.",
        "Адресу самовивозу ще не опубліковано. Крамниця напише вам щодо цього замовлення.",
    ),
}


def shop_timezone() -> str | None:
    """The clock the shop's own times are printed in, or None while it is unset."""
    return (os.getenv("SHOP_TIMEZONE") or "").strip() or None


def when_text(moment: datetime) -> str:
    """One instant, written so it cannot be misread: date, time, and the zone it is in."""
    tz_name = shop_timezone()
    if tz_name:
        try:
            from zoneinfo import ZoneInfo

            local = moment.astimezone(ZoneInfo(tz_name))
            return f"{local:%Y-%m-%d %H:%M} {local.tzname() or tz_name}"
        except Exception:  # noqa: BLE001 - an unknown zone name falls back to UTC
            log.warning("SHOP_TIMEZONE=%r is not a zone this machine knows; printing UTC", tz_name)
    return f"{moment.astimezone(timezone.utc):%Y-%m-%d %H:%M} UTC"


def _utc(value: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes; every time this module prints is UTC-anchored."""
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _forget_expired_code(db: Session, order_id: str) -> None:
    """Erase the digits of a credential that ran out of hours, and keep the write small.

    Every caller of the order view commits its own work before it gets here, so this
    commit carries nothing but the erased column. A database that refuses it leaves the
    page working and the row unchanged.
    """
    try:
        if locker.forget_expired_display_codes(db, order_id=order_id):
            db.commit()
    except Exception as exc:  # noqa: BLE001 - reading an order page must not fail on this
        log.warning("could not erase an expired pickup code order=%s error=%s: %s",
                    order_id, type(exc).__name__, exc)
        db.rollback()


def pickup_view(db: Session, order: Order) -> dict | None:
    """The pickup block on the order page. None for an order that is being shipped."""
    if (order.fulfillment_method or "") != "PICKUP":
        return None
    cfg = locker.pickup_config()
    live = locker.live_customer_access(db, order.id)
    # The credential this page speaks about: the live one when there is one, otherwise the
    # last one this order ever had, which is what the "expired" and "withdrawn" copy is for.
    access = live or locker.latest_customer_access(db, order.id)
    package = db.scalar(select(Package).where(Package.order_id == order.id))
    bay_id = (access.bay_id if access else None) or (package.bay_id if package else None)

    if order.state == "HANDOFF_COMPLETE":
        state = "collected"          # the parcel has left the bay
    elif access is None:
        state = "preparing"          # the parcel is not in a bay yet
    elif access.used_at is not None:
        state = "opened"             # this code opened the bay and is spent
    elif access.revoked_at is not None:
        state = "withdrawn"          # the shop took the code back
    elif live is not None:
        state = "ready"              # the code below works
    else:
        state = "expired"            # the code ran out of hours unused

    if state == "expired":
        # The hours ran out with nobody spending the code. The digits stop being readable
        # here, the way they are erased when a code is spent or withdrawn.
        _forget_expired_code(db, order.id)

    if state == "preparing":
        copy_key = "preparing_mail" if notifications_config()["email"] else "preparing_nomail"
    else:
        copy_key = state
    if not cfg["address_configured"] and state in {"preparing", "ready"}:
        copy_key = "no_address"

    valid_until = _utc(access.valid_until) if access else None
    return {
        "state": state,
        "label": cfg["label"],
        "label_uk": cfg["label_uk"],
        "address": cfg["address"],
        "hours": cfg["hours"],
        "note": cfg["note"],
        "bay": bay_id,
        # Only a live credential has a code, and only the customer who proved the order
        # number and the email address of this order ever reaches this view.
        "code": live.display_code if live else None,
        "valid_from": _iso(_utc(live.valid_from)) if live else None,
        "valid_until": _iso(valid_until),
        "valid_until_text": when_text(valid_until) if (live and valid_until) else None,
        "valid_hours": cfg["code_valid_hours"],
        "message": PICKUP_COPY[copy_key][0],
        "message_uk": PICKUP_COPY[copy_key][1],
    }


def order_view(db: Session, order: Order) -> dict:
    lines = []
    for line in order.lines:
        v = db.get(Variant, line.variant_id)
        product = db.get(Product, v.product_id) if v and v.product_id else None
        maker = db.get(Maker, product.maker_id) if product and product.maker_id else None
        lines.append({
            "sku": v.sku if v else None,
            "maker": maker.name if maker else None,
            "maker_uk": maker.name_uk if maker else None,
            "title": product.title if product else (v.name if v else "Item"),
            "title_uk": product.title_uk if product else None,
            "label": (v.option_label if v else None),
            "label_uk": (v.option_label_uk if v else None),
            "product_slug": product.slug if product else None,
            "image_url": product.image_url if product else None,
            "origin": product.origin if product else None,
            "qty": line.qty,
            "unit_price_cad": round(float(line.unit_price_cad), 2),
            "line_total_cad": round(line.qty * float(line.unit_price_cad), 2),
        })
    key, label, label_uk = CUSTOMER_STATES.get(order.state, ("processing", "In progress", "У роботі"))
    if (order.fulfillment_method or "") == "PICKUP" and order.state in PICKUP_STATES:
        key, label, label_uk = PICKUP_STATES[order.state]
    package = db.scalar(select(Package).where(Package.order_id == order.id))
    shipment = db.scalar(select(ShipmentRecord).where(ShipmentRecord.package_id == package.id)) if package else None
    return {
        "order_number": order.order_number,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "status": {"key": key, "label": label, "label_uk": label_uk, "raw": order.state},
        "customer": {"email": order.customer_email, "name": order.customer_name, "phone": order.customer_phone},
        "fulfillment_method": order.fulfillment_method,
        "ship_to": json.loads(order.ship_to_json or "{}"),
        "pickup": pickup_view(db, order),
        "lines": lines,
        "totals": {
            "subtotal_cad": order.subtotal_cad,
            "shipping_cad": order.shipping_cad,
            "tax_cad": order.tax_cad,
            "tax_rate": order.tax_rate,
            "tax_lines": _stored_tax_lines(order),
            "total_cad": order.gross_amount_cad,
        },
        "gst_number": taxes.gst_number(),
        "payment": payment_instructions(order),
        "demo": bool(order.is_demo),
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
        "tracking": {
            "carrier": shipment.carrier if shipment else None,
            "code": shipment.tracking_code if shipment else None,
        } if shipment and shipment.tracking_code else None,
        "note": order.customer_note or "",
    }


def _stored_tax_lines(order: Order) -> list[dict]:
    """The named lines frozen at placement. An older order with one rate gets one line."""
    try:
        lines = json.loads(order.tax_lines_json or "[]")
    except ValueError:
        lines = []
    if lines:
        return lines
    if order.tax_cad and order.tax_rate:
        pct = f"{round(float(order.tax_rate) * 100, 3):g}%"
        return [{"code": "TAX", "label": f"Sales tax ({pct})", "label_uk": f"Податок з продажу ({pct})",
                 "rate": order.tax_rate, "amount_cad": order.tax_cad}]
    return []


def find_order_by_token(db: Session, order_number: str, token: str) -> Order:
    """The order this number names, when `token` is its access key. Constant-time compare."""
    order = db.scalar(select(Order).where(Order.order_number == (order_number or "").strip().upper()))
    supplied = (token or "").strip()
    if not order or not order.access_token or not supplied or not hmac.compare_digest(order.access_token, supplied):
        raise StorefrontError("Order not found", code="not_found")
    return order


def find_order_for_customer(db: Session, order_number: str, email: str) -> Order:
    order = db.scalar(select(Order).where(Order.order_number == order_number.strip().upper()))
    if not order or (order.customer_email or "").lower() != (email or "").strip().lower():
        raise StorefrontError("Order not found", code="not_found")
    return order


# --------------------------------------------------------------------------- stripe (no SDK)

STRIPE_API = "https://api.stripe.com/v1"
FAKE_SESSION_PREFIX = "cs_test_fake_"
# The fake provider signs its own webhook with this key. It lives for one process and is
# never configured, so nothing outside the running API can forge a fake payment with it.
_FAKE_WEBHOOK_SECRET = secrets.token_hex(32)


def stripe_enabled() -> bool:
    """Real card payments: both the key and the webhook secret, and not the fake provider."""
    if payment_provider() == "fake":
        return False
    return bool(os.getenv("STRIPE_SECRET_KEY", "").strip() and os.getenv("STRIPE_WEBHOOK_SECRET", "").strip())


def amount_cents(order: Order) -> int:
    return int(round(float(order.gross_amount_cad or 0) * 100))


def order_page_return_url(order: Order, *, paid: bool) -> str:
    base = os.getenv("WEB_BASE_URL", "http://localhost:3000").strip().rstrip("/")
    lang = "" if (order.locale or "en") == "en" else f"/{order.locale}"
    query = urlencode({"key": order.access_token or "", **({"paid": "1"} if paid else {})})
    return f"{base}{lang}/order/{order.order_number}?{query}"


def ensure_stock_for_payment(db: Session, order: Order) -> None:
    """A card session opens only while the goods are held for this order.

    A hold that lapsed is taken again when the stock is still free. When it is not, no
    session is opened: the buyer would pay for something the shop cannot send.
    """
    if holds_cover_order(db, order):
        order.hold_expires_at = now_utc() + timedelta(minutes=order_hold_minutes())
        return
    release_holds(db, order)
    try:
        hold_stock(db, order, until=now_utc() + timedelta(minutes=order_hold_minutes()))
    except InventoryError:
        raise StorefrontError("Some items sold out while this order waited for payment", code="out_of_stock")


def open_checkout(db: Session, order: Order, *, client: httpx.Client | None = None) -> str | None:
    """Open a card payment session for an unpaid STRIPE order and return where to send the buyer.

    Real Stripe sessions are never opened for demonstration orders. Returns None when there
    is nothing to open.
    """
    if order.payment_method != "STRIPE" or order.state != "AWAITING_PAYMENT":
        return None
    if fake_payments_enabled():
        ensure_stock_for_payment(db, order)
        return create_fake_checkout(order)
    if order.is_demo or not stripe_enabled():
        return None
    ensure_stock_for_payment(db, order)
    return create_stripe_checkout(
        db, order, success_url=order_page_return_url(order, paid=True),
        cancel_url=order_page_return_url(order, paid=False), client=client,
    )


def create_fake_checkout(order: Order) -> str:
    """A local "Pay (test)" page on the storefront. No money, no network."""
    session_id = FAKE_SESSION_PREFIX + secrets.token_urlsafe(18)
    base = os.getenv("WEB_BASE_URL", "http://localhost:3000").strip().rstrip("/")
    lang = "" if (order.locale or "en") == "en" else f"/{order.locale}"
    url = f"{base}{lang}/pay/test/{session_id}"
    order.checkout_session_id = session_id
    order.payment_ref = url
    return url


def create_stripe_checkout(db: Session, order: Order, *, success_url: str, cancel_url: str, client: httpx.Client | None = None) -> str:
    """Create a Stripe Checkout Session for an AWAITING_PAYMENT order; returns the hosted URL."""
    if not stripe_enabled():
        raise StorefrontError("Stripe is not configured", code="payment_method")
    if order.state != "AWAITING_PAYMENT":
        raise StorefrontError("Order is not awaiting payment", code="state")
    # Stripe accepts an expiry between 30 minutes and 24 hours out.
    expires = int(time.time()) + max(31, order_hold_minutes()) * 60
    form: list[tuple[str, str]] = [
        ("mode", "payment"),
        ("client_reference_id", order.id),
        ("customer_email", order.customer_email or ""),
        ("success_url", success_url),
        ("cancel_url", cancel_url),
        ("expires_at", str(expires)),
        ("metadata[order_number]", order.order_number or ""),
        ("payment_method_types[0]", "card"),
    ]
    i = 0
    for line in order.lines:
        v = db.get(Variant, line.variant_id)
        product = db.get(Product, v.product_id) if v and v.product_id else None
        name = f"{product.title} — {v.option_label}" if product and v.option_label else (product.title if product else v.name)
        form += [
            (f"line_items[{i}][price_data][currency]", "cad"),
            (f"line_items[{i}][price_data][unit_amount]", str(int(round(float(line.unit_price_cad) * 100)))),
            (f"line_items[{i}][price_data][product_data][name]", name[:250]),
            (f"line_items[{i}][quantity]", str(line.qty)),
        ]
        i += 1
    for label, amount in (("Shipping", order.shipping_cad or 0), ("Tax", order.tax_cad or 0)):
        if amount and amount > 0:
            form += [
                (f"line_items[{i}][price_data][currency]", "cad"),
                (f"line_items[{i}][price_data][unit_amount]", str(int(round(amount * 100)))),
                (f"line_items[{i}][price_data][product_data][name]", label),
                (f"line_items[{i}][quantity]", "1"),
            ]
            i += 1
    own_client = client is None
    client = client or httpx.Client(timeout=20)
    try:
        resp = client.post(
            f"{STRIPE_API}/checkout/sessions",
            content=urlencode(form),
            headers={
                "Authorization": f"Bearer {os.getenv('STRIPE_SECRET_KEY').strip()}",
                "Content-Type": "application/x-www-form-urlencoded",
                # One key per attempt: a retry after an expired session needs a new session,
                # and the same key would hand back the expired one.
                "Idempotency-Key": f"checkout-{order.id}-{secrets.token_hex(6)}",
            },
        )
    finally:
        if own_client:
            client.close()
    if resp.status_code >= 300:
        raise StorefrontError("Stripe refused to open checkout", code="stripe", details={"status": resp.status_code})
    data = resp.json()
    url = data.get("url")
    if not url:
        raise StorefrontError("Stripe returned no checkout URL", code="stripe")
    order.payment_ref = url
    order.checkout_session_id = data.get("id") or order.checkout_session_id
    return url


def verify_stripe_signature(raw: bytes, header: str, secret: str, *, tolerance: int = 300, now: float | None = None) -> bool:
    if not header or not secret:
        return False
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    ts = parts.get("t")
    v1 = parts.get("v1")
    if not ts or not v1:
        return False
    try:
        ts_int = int(ts)
    except ValueError:
        return False
    now = time.time() if now is None else now
    if abs(now - ts_int) > tolerance:
        return False
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, v1)


def sign_stripe_payload(raw: bytes, secret: str, *, timestamp: int | None = None) -> str:
    ts = int(time.time()) if timestamp is None else timestamp
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + raw, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


PAYMENT_MISMATCH = "PAYMENT_AMOUNT_MISMATCH"


def apply_stripe_event(db: Session, event: dict) -> Order | None:
    """Apply one Stripe Checkout event to its order.

    * checkout.session.completed with payment_status paid: the amount and currency must be
      exactly this order's total in CAD, then the order is marked paid (which reserves it).
    * checkout.session.expired for the order's current session: the stock hold is released
      and the dead checkout link is forgotten, so the order page offers a new payment.
    """
    kind = event.get("type")
    if kind not in {"checkout.session.completed", "checkout.session.expired"}:
        return None
    session = (event.get("data") or {}).get("object") or {}
    order_id = session.get("client_reference_id")
    order = db.get(Order, order_id) if order_id else None
    if not order or order.channel != "WEB":
        return None
    if kind == "checkout.session.expired":
        if order.state == "AWAITING_PAYMENT" and session.get("id") and session.get("id") == order.checkout_session_id:
            release_holds(db, order)
            order.payment_ref = None
        return order
    if session.get("payment_status") not in {"paid", "no_payment_required"}:
        return None
    if order.paid_at is not None:
        return order
    expected = amount_cents(order)
    amount = session.get("amount_total")
    currency = (session.get("currency") or "").lower()
    if amount != expected or currency != "cad":
        raise StorefrontError(
            "Paid amount does not match the order", code="amount_mismatch",
            details={"order_number": order.order_number, "expected_cents": expected, "amount_total": amount,
                     "currency": currency or None, "session": session.get("id")},
        )
    return mark_paid(db, order, reference=session.get("payment_intent") or session.get("id"), method="STRIPE")


def record_payment_mismatch(db: Session, exc: StorefrontError) -> None:
    details = exc.details or {}
    open_exception(
        db, kind=PAYMENT_MISMATCH, reference_type="ORDER_NUMBER",
        reference_id=str(details.get("order_number") or "unknown")[:120],
        details=json.dumps({"summary": f"A payment arrived with the wrong amount or currency. Check {'PayPal' if details.get('provider') == 'PAYPAL' else 'Stripe'} and refund or settle by hand.", **details}),
    )


def fake_session_order(db: Session, session_id: str) -> Order:
    if not fake_payments_enabled() or not session_id.startswith(FAKE_SESSION_PREFIX):
        raise StorefrontError("Payment session not found", code="not_found")
    order = db.scalar(select(Order).where(Order.checkout_session_id == session_id))
    if not order:
        raise StorefrontError("Payment session not found", code="not_found")
    return order


def fake_session_view(db: Session, session_id: str) -> dict:
    order = fake_session_order(db, session_id)
    return {
        "session_id": session_id,
        "order_number": order.order_number,
        "locale": order.locale or "en",
        "amount_cad": order.gross_amount_cad,
        "currency": "CAD",
        "state": order.state,
        "paid": order.paid_at is not None,
        "demo": bool(order.is_demo),
        "return_url": order_page_return_url(order, paid=order.paid_at is not None),
    }


def fake_webhook_body(db: Session, session_id: str, *, kind: str = "checkout.session.completed") -> tuple[bytes, str]:
    """The event Stripe would send for this session, signed the way Stripe signs it."""
    order = fake_session_order(db, session_id)
    event = {
        "id": f"evt_test_fake_{secrets.token_hex(8)}",
        "type": kind,
        "livemode": False,
        "data": {"object": {
            "id": session_id,
            "object": "checkout.session",
            "client_reference_id": order.id,
            "payment_status": "paid" if kind == "checkout.session.completed" else "unpaid",
            "amount_total": amount_cents(order),
            "currency": "cad",
            "payment_intent": f"pi_test_fake_{secrets.token_hex(8)}",
        }},
    }
    raw = json.dumps(event).encode()
    return raw, sign_stripe_payload(raw, _FAKE_WEBHOOK_SECRET)


def fake_webhook_secret() -> str:
    return _FAKE_WEBHOOK_SECRET


# --------------------------------------------------------------------------- order email
#
# One email per (order, kind), and the proof that it happened lives in the outbox table
# next to every other durable message the system sends:
#
#   topic            notify/email
#   idempotency_key  mail:<kind>:<order id>
#   state            PENDING  — nothing went out yet, a sweep may retry it
#                    DELIVERED — the SMTP server accepted it
#                    SKIPPED  — email was switched off when this order reached this point
#                    FAILED   — MAIL_MAX_ATTEMPTS tries failed; an operator has an exception row
#
# Sending happens after the order transaction commits, so a mail server that is slow, down
# or misconfigured can never roll an order back or hold a customer at the checkout button.

MAIL_TOPIC = "notify/email"
MAIL_KINDS = mailer.KINDS  # ("placed", "paid", "pickup_ready", "handoff", "cancelled")
MAIL_MAX_ATTEMPTS = 5
MAIL_MAX_AGE_DAYS_DEFAULT = 14
MAIL_EXCEPTION_KIND = "ORDER_EMAIL_FAILED"


def notifications_config() -> dict:
    """What the storefront may say about email. Never exposes host, login or password."""
    cfg = mailer.load_config()
    if cfg.enabled and cfg.local_capture and _public_base_url():
        # Mailpit catches every message and delivers none. A buyer who reached the shop at a
        # public address (the hosted demo) will never see it, so nothing is promised.
        return {"email": False, "from_email": None}
    return {"email": cfg.enabled, "from_email": mailer.sender_address(cfg)}


def _public_base_url() -> bool:
    """True when WEB_BASE_URL names a host outside this machine (not localhost or 127.0.0.1)."""
    from urllib.parse import urlsplit
    host = (urlsplit((os.getenv("WEB_BASE_URL") or "").strip()).hostname or "").lower()
    return bool(host) and host not in {"localhost", "127.0.0.1", "::1"} and not host.endswith(".localhost")


def mail_max_age_days() -> int:
    """How far back a sweep may reach. Stops a first-time SMTP switch-on from mailing history."""
    try:
        return max(0, int(os.getenv("ORDER_MAIL_MAX_AGE_DAYS", "").strip()))
    except ValueError:
        return MAIL_MAX_AGE_DAYS_DEFAULT


def order_page_url(order: Order) -> str | None:
    """The customer's own order page, or None while WEB_BASE_URL is unset."""
    base = os.getenv("WEB_BASE_URL", "").strip().rstrip("/")
    if not base or not order.order_number:
        return None
    lang = "" if (order.locale or "en") == "en" else f"/{order.locale}"
    query = urlencode({"key": order.access_token or ""})
    return f"{base}{lang}/order/{order.order_number}?{query}"


def terms_url(order: Order) -> str | None:
    """The terms of sale in the buyer's language, or None while WEB_BASE_URL is unset."""
    base = os.getenv("WEB_BASE_URL", "").strip().rstrip("/")
    if not base:
        return None
    lang = "" if (order.locale or "en") == "en" else f"/{order.locale}"
    return f"{base}{lang}/terms"


def mail_key(order_id: str, kind: str) -> str:
    return f"mail:{kind}:{order_id}"


def render_order_mail(db: Session, order: Order, kind: str, *, config: mailer.MailerConfig | None = None) -> mailer.EmailContent:
    """The message this order would produce, in the customer's own locale."""
    cfg = config or mailer.load_config()
    lang = (order.locale or "en").lower()
    shop = storefront_config()
    pickup_label = None
    if order.fulfillment_method == "PICKUP":
        pickup_label = shop["pickup"]["label_uk"] if lang == "uk" else shop["pickup"]["label"]
    view = order_view(db, order)
    if kind == "placed":
        # "Order received" says what was true at placement, whenever it is (re)sent.
        try:
            frozen = json.loads(order.placement_json or "{}")
        except ValueError:
            frozen = {}
        if frozen.get("payment"):
            view["payment"] = frozen["payment"]
            view["status"] = {"key": "awaiting_payment", "label": CUSTOMER_STATES["AWAITING_PAYMENT"][1],
                              "label_uk": CUSTOMER_STATES["AWAITING_PAYMENT"][2], "raw": "AWAITING_PAYMENT"}
            view["tracking"] = None
    return mailer.render_order_email(
        view,
        kind=kind,
        lang=lang,
        shop_name=cfg.shop_name,
        order_url=order_page_url(order),
        pickup_label=pickup_label,
        contact_email=shop["contact_email"],
        terms_url=terms_url(order),
        terms_version=terms_version(),
    )


def notify_order(
    db: Session, order: Order, kind: str, *,
    transport: "mailer.Transport | None" = None, commit: bool = True,
    resend: bool = False,
) -> mailer.SendResult | None:
    """Send one order email, at most once per (order, kind). Call it after the commit.

    Returns None when there was nothing to do (already handled, or not a web order with a
    customer email). No mail failure escapes: a refused server, a bad login or a timeout
    becomes an ORDER_EMAIL_FAILED row on the operator dashboard and the order carries on.
    The one exception it does raise is a caller passing a kind that does not exist.

    ``resend`` re-opens a message that was already handled, and there is exactly one caller:
    an operator minting a fresh bay code for a parcel that is already in the locker. The
    customer is written to again because the code they were sent no longer works. Nothing
    automatic ever sets it, so no customer is written to twice by a sweep or a retry.
    """
    if kind not in MAIL_KINDS:
        raise ValueError(f"unknown mail kind {kind!r}")
    if order.channel != "WEB" or not order.customer_email or not order.order_number:
        return None
    if kind == "pickup_ready" and not locker.live_customer_access(db, order.id):
        # Nothing to carry: no live code means no "your parcel is in the locker" message.
        return None
    row = None
    try:
        key = mail_key(order.id, kind)
        row = db.scalar(select(OutboxMessage).where(OutboxMessage.idempotency_key == key))
        if row is not None and row.state != "PENDING":
            if not resend:
                return None
            # Re-open the message and commit that before talking to the mail server, the
            # way a first send claims it. One row per (order, kind) either way, so the
            # dashboard shows the latest attempt rather than a growing pile.
            row.state = "PENDING"
            row.attempt_count = 0
            row.delivered_at = None
            if commit:
                db.commit()
        cfg = mailer.load_config()
        content = render_order_mail(db, order, kind, config=cfg)
        if row is None:
            row = enqueue(
                db, topic=MAIL_TOPIC, event_type=f"ORDER_MAIL_{kind.upper()}", aggregate_type="ORDER",
                aggregate_id=order.id,
                payload={"order_id": order.id, "order_number": order.order_number, "kind": kind,
                         "to": order.customer_email, "locale": (order.locale or "en").lower(),
                         "subject": content.subject},
                idempotency_key=key,
            )
            if commit:
                # Claim the message before talking to the mail server. Two requests racing
                # for the same message collide on the unique key here, and the one that
                # loses never sends, so the customer is not written to twice.
                db.commit()
        result = mailer.send_content(content, to=order.customer_email, config=cfg, transport=transport)
        if result.sent:
            acknowledge(db, row)
        elif result.disabled:
            # Email is switched off. The row records that this customer was not written to,
            # and switching SMTP on later starts with the orders that come after it.
            row.state = "SKIPPED"
            row.attempt_count += 1
        else:
            row.attempt_count += 1
            if row.attempt_count >= MAIL_MAX_ATTEMPTS:
                row.state = "FAILED"
            open_exception(
                db, kind=MAIL_EXCEPTION_KIND, reference_type="ORDER", reference_id=order.id,
                details=json.dumps({
                    "order_number": order.order_number, "kind": kind, "to": order.customer_email,
                    "attempts": row.attempt_count, "stopped": row.state == "FAILED", "error": result.error,
                }, ensure_ascii=False),
            )
        if commit:
            db.commit()
        return result
    except Exception as exc:  # noqa: BLE001 - notification failure must never reach the order
        log.warning("order mail failed order=%s kind=%s error=%s: %s",
                    order.order_number, kind, type(exc).__name__, exc)
        if commit:
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                pass
        return None


def mail_kinds_due(db: Session, order: Order) -> list[str]:
    """Which emails this order has earned, by its own state. Nothing is inferred beyond it."""
    if order.channel != "WEB" or not order.customer_email or not order.order_number:
        return []
    kinds: list[str] = []
    if order.state != "CANCELLED":
        kinds.append("placed")
    if order.paid_at:
        kinds.append("paid")
    # The pickup notice is due only while there is a code to put in it. A credential that
    # has been used, revoked or has run out of hours earns no email, because the message
    # exists to carry a code the customer can still type at the door.
    if (order.fulfillment_method or "") == "PICKUP" and locker.live_customer_access(db, order.id):
        kinds.append("pickup_ready")
    if order.state == "HANDOFF_COMPLETE":
        kinds.append("handoff")
    if order.state == "CANCELLED":
        kinds.append("cancelled")
    return kinds


def order_mail_backlog(db: Session, *, limit: int = 50) -> list[tuple[Order, str]]:
    """Order emails that are due and have not been handled, newest orders first."""
    cutoff = now_utc() - timedelta(days=mail_max_age_days())
    orders = list(db.scalars(
        select(Order)
        .where(Order.channel == "WEB", Order.created_at >= cutoff)
        .order_by(Order.created_at.desc())
        .limit(400)
    ))
    if not orders:
        return []
    handled = set(db.scalars(
        select(OutboxMessage.idempotency_key).where(
            OutboxMessage.topic == MAIL_TOPIC,
            OutboxMessage.aggregate_id.in_([o.id for o in orders]),
            OutboxMessage.state.in_(["DELIVERED", "SKIPPED", "FAILED"]),
        )
    ))
    due: list[tuple[Order, str]] = []
    for order in orders:
        for kind in mail_kinds_due(db, order):
            if len(due) >= limit:
                return due
            if mail_key(order.id, kind) not in handled:
                due.append((order, kind))
    return due


def dispatch_order_mail(db: Session, *, limit: int = 50, transport: "mailer.Transport | None" = None) -> dict:
    """Send every order email that is due: retries, and the handoff notice.

    The placed and paid messages go out from the storefront API the moment they happen.
    Handoff is written by the warehouse side of the pipeline, which has no mail hook, so
    this sweep is what turns "handed to the courier" into an email. Run it on a timer.
    """
    counts = {"considered": 0, "sent": 0, "skipped": 0, "failed": 0}
    for order, kind in order_mail_backlog(db, limit=limit):
        counts["considered"] += 1
        result = notify_order(db, order, kind, transport=transport)
        if result is None:
            continue
        if result.sent:
            counts["sent"] += 1
        elif result.disabled:
            counts["skipped"] += 1
        else:
            counts["failed"] += 1
    return counts
