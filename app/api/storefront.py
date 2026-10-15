"""Public storefront API (no API key): catalogue reads, web orders, order status, PayPal and Stripe webhooks."""
from __future__ import annotations

import json
import os

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import require_operator
from ..deps import get_db
from ..models import Order
from ..schemas import MarkPaidIn, OrderLookupIn, PayPalCaptureIn, QuoteIn, ShipIn, WebOrderIn
from ..services import paypal
from ..services.catalog import CatalogError, get_maker, get_product, list_categories, list_collections, list_makers, list_products
from ..services.ratelimit import client_address, lookup_limiter, order_invalid_limiter, order_limiter
from ..services.locker import sweep_expired_pickup_codes
from ..services.orders import OrderError, ship_order
from ..services.storefront import (
    MAIL_KINDS, StorefrontError, apply_stripe_event, cancel_unpaid, create_web_order, dispatch_order_mail,
    fake_session_view, fake_webhook_body, fake_webhook_secret, find_order_by_token, find_order_for_customer, freeze_placement,
    mark_paid, notify_order, open_checkout, order_view, quote as quote_service, record_payment_mismatch, record_terms_acceptance,
    release_expired_holds, render_order_mail, storefront_config, verify_stripe_signature,
)

router = APIRouter()


# The limiters below are keyed by the caller's address, read by the same function the two
# locker doors read it with (app/services/ratelimit.py). A client address header counts only
# with the internal proxy secret the storefront server adds; otherwise one header would let a
# caller pick a fresh key for every request and the cap would guard nothing.

# Codes that mean "the form was filled in wrong". They count in their own bucket.
VALIDATION_CODES = {"email", "name", "fulfillment_method", "ship_to", "payment_method", "lines", "idempotency_key",
                    "province_excluded"}


def _err(exc: StorefrontError, status: int = 400):
    return HTTPException(status, {"code": exc.code, "message": str(exc), **({"details": exc.details} if exc.details else {})})


# ------------------------------------------------------------------ catalogue

@router.get("/v1/storefront/config")
def config():
    return storefront_config()


@router.get("/v1/catalog/products")
def products(
    category: str | None = None,
    collection: str | None = None,
    maker: str | None = None,
    q: str | None = Query(default=None, max_length=80),
    featured: bool | None = None,
    in_stock: bool | None = None,
    sort: str = Query(default="position", pattern="^(position|price_asc|price_desc|newest)$"),
    limit: int = Query(default=60, ge=1, le=120),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    return list_products(db, category=category, collection=collection, maker=maker, q=q, featured=featured,
                         in_stock=in_stock, sort=sort, limit=limit, offset=offset)


@router.get("/v1/catalog/products/{slug}")
def product(slug: str, db: Session = Depends(get_db)):
    try:
        return get_product(db, slug)
    except CatalogError as exc:
        raise HTTPException(404, str(exc))


@router.get("/v1/catalog/collections")
def collections(db: Session = Depends(get_db)):
    return {"items": list_collections(db)}


@router.get("/v1/catalog/categories")
def categories(db: Session = Depends(get_db)):
    return {"items": list_categories(db)}


@router.get("/v1/catalog/makers")
def makers(db: Session = Depends(get_db)):
    return {"items": list_makers(db)}


@router.get("/v1/catalog/makers/{slug}")
def maker(slug: str, db: Session = Depends(get_db)):
    try:
        return get_maker(db, slug)
    except CatalogError as exc:
        raise HTTPException(404, str(exc))


# ------------------------------------------------------------------ orders

@router.post("/v1/storefront/quote")
def quote(inp: QuoteIn, db: Session = Depends(get_db)):
    """Totals and per-line availability for the bag. Prices are re-read from the database.

    Each line carries `status` (ok | reduce | sold_out) and `max_qty`, the most the shop can
    send of it right now. No stock count beyond that is exposed.
    """
    return quote_service(
        db,
        lines=[line.model_dump() for line in inp.lines],
        fulfillment_method=inp.fulfillment_method,
        province=(inp.ship_to.province if inp.ship_to else None),
    )


@router.post("/v1/storefront/orders", status_code=201)
def place_order(inp: WebOrderIn, request: Request, db: Session = Depends(get_db)):
    ip = client_address(request)
    if order_limiter.would_block(ip):
        raise HTTPException(429, {"code": "rate_limited", "message": "Too many attempts, try again in a few minutes"})
    payload = inp.model_dump()
    try:
        order, duplicate = create_web_order(db, payload)
        db.flush()
        checkout_url = None
        if order.payment_method == "STRIPE" and not duplicate:
            checkout_url = open_checkout(db, order)
            freeze_placement(order)
        if inp.terms_accepted and not duplicate:
            record_terms_acceptance(order)
        db.commit()
    except StorefrontError as exc:
        db.rollback()
        if exc.code in VALIDATION_CODES:
            if not order_invalid_limiter.allow(ip):
                raise HTTPException(429, {"code": "rate_limited", "message": "Too many attempts, try again in a few minutes"})
        else:
            order_limiter.allow(ip)
        raise _err(exc, 409 if exc.code in {"out_of_stock", "state", "not_taking_orders"} else 400)
    except IntegrityError:
        db.rollback()
        order_limiter.allow(ip)
        raise HTTPException(409, {"code": "conflict", "message": "Order could not be saved, retry"})
    order_limiter.allow(ip)
    view = order_view(db, order)
    if checkout_url:
        view["payment"]["checkout_url"] = checkout_url
    view["duplicate"] = duplicate
    # Only the request that created the order (or its idempotent retry) learns the key.
    view["access_token"] = order.access_token
    # The order is durable at this point. The confirmation goes out after the commit, so a
    # mail server that is down cannot undo an order the customer already paid attention to.
    notify_order(db, order, "placed")
    return view


def _customer_order(db: Session, order_number: str, token: str | None, email: str | None) -> Order:
    """The buyer proves the order with its access key (the web) or the email it was placed with."""
    if token:
        return find_order_by_token(db, order_number, token)
    return find_order_for_customer(db, order_number, email or "")


@router.post("/v1/storefront/orders/lookup")
def order_lookup(inp: OrderLookupIn, request: Request, db: Session = Depends(get_db)):
    """Order number and email in the body, the order's access key back. Nothing in a URL."""
    if not lookup_limiter.allow(client_address(request)):
        raise HTTPException(429, {"code": "rate_limited", "message": "Too many lookups"})
    try:
        order = find_order_for_customer(db, inp.order_number, inp.email)
    except StorefrontError as exc:
        raise _err(exc, 404)
    if not order.access_token:
        from ..services.storefront import new_access_token
        order.access_token = new_access_token()
        db.commit()
    return {"order_number": order.order_number, "access_token": order.access_token, "locale": order.locale or "en"}


@router.get("/v1/storefront/orders/{order_number}")
def order_status(order_number: str, request: Request, email: str | None = None,
                 x_order_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    if not lookup_limiter.allow(client_address(request)):
        raise HTTPException(429, {"code": "rate_limited", "message": "Too many lookups"})
    try:
        order = _customer_order(db, order_number, x_order_token, email)
    except StorefrontError as exc:
        raise _err(exc, 404)
    return order_view(db, order)


@router.post("/v1/storefront/orders/{order_number}/cancel")
def order_cancel(order_number: str, request: Request, email: str | None = None,
                 x_order_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    if not order_limiter.allow(client_address(request)):
        raise HTTPException(429, {"code": "rate_limited", "message": "Too many attempts"})
    try:
        order = _customer_order(db, order_number, x_order_token, email)
        cancel_unpaid(db, order)
        db.commit()
    except StorefrontError as exc:
        db.rollback()
        raise _err(exc, 404 if exc.code == "not_found" else 409)
    notify_order(db, order, "cancelled")
    return order_view(db, order)


@router.post("/v1/storefront/orders/{order_number}/pay")
def order_retry_payment(order_number: str, request: Request, email: str | None = None,
                        x_order_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    """Open a new card payment session for an unpaid order whose last one expired or was abandoned."""
    if not order_limiter.allow(client_address(request)):
        raise HTTPException(429, {"code": "rate_limited", "message": "Too many attempts"})
    try:
        order = _customer_order(db, order_number, x_order_token, email)
        if order.state != "AWAITING_PAYMENT":
            raise StorefrontError(f"Order is {order.state}, not awaiting payment", code="state")
        if order.payment_method != "STRIPE":
            raise StorefrontError("This order is not paid by card", code="payment_method")
        url = open_checkout(db, order)
        if not url:
            raise StorefrontError("Card payment is not available for this order", code="payment_method")
        db.commit()
    except StorefrontError as exc:
        db.rollback()
        raise _err(exc, 404 if exc.code == "not_found" else 409)
    view = order_view(db, order)
    view["payment"]["checkout_url"] = url
    return view


# ------------------------------------------------------------------ local test payments
#
# PAYMENT_PROVIDER=fake only. The storefront's "Pay (test)" page reads the session and
# completes it; completion builds the event Stripe would send, signs it, and runs it through
# the same verification and the same apply_stripe_event as /webhooks/stripe.

@router.get("/v1/payments/test/{session_id}")
def test_payment_session(session_id: str, db: Session = Depends(get_db)):
    try:
        return fake_session_view(db, session_id)
    except StorefrontError as exc:
        raise _err(exc, 404)


@router.post("/v1/payments/test/{session_id}/complete")
def test_payment_complete(session_id: str, db: Session = Depends(get_db)):
    try:
        raw, signature = fake_webhook_body(db, session_id)
    except StorefrontError as exc:
        raise _err(exc, 404)
    result = _process_stripe_webhook(db, raw, signature, fake_webhook_secret())
    return {**result, **fake_session_view(db, session_id)}


# ------------------------------------------------------------------ operator side

@router.post("/v1/orders/{order_id}/mark-paid", dependencies=[Depends(require_operator)])
def operator_mark_paid(order_id: str, inp: MarkPaidIn, db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    try:
        mark_paid(db, order, reference=inp.reference, method=inp.method)
        db.commit()
    except StorefrontError as exc:
        db.rollback()
        raise _err(exc, 409)
    if order.paid_at is not None:
        notify_order(db, order, "paid")
    return {"order_id": order.id, "order_number": order.order_number, "state": order.state, "paid_at": order.paid_at.isoformat() if order.paid_at else None}


@router.post("/v1/notifications/order-mail", dependencies=[Depends(require_operator)])
def dispatch_notifications(limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)):
    """Send the order emails that are due: retries after a mail failure, and the handoff
    notice, which the warehouse side of the pipeline has no hook to send itself.

    Safe to call on a timer: every message is claimed in the outbox before it is sent, so a
    second call sends nothing twice. `email` says whether the shop can send at all.
    """
    counts = dispatch_order_mail(db, limit=limit)
    # The same timer is where a pickup code that outlived its window loses its readable
    # digits. Until this ran here, the only thing that erased them was the buyer opening
    # their own order page, so a code nobody came for kept its digits in the database
    # indefinitely.
    forgotten = sweep_expired_pickup_codes(db)
    holds = release_expired_holds(db)
    db.commit()
    tracking = paypal.sync_pending_tracking(db)
    db.commit()
    return {"email": storefront_config()["notifications"]["email"], **counts, "pickup_codes_forgotten": forgotten,
            "holds_released": holds, "paypal_tracking_pushed": tracking}


@router.post("/v1/orders/{order_id}/ship", dependencies=[Depends(require_operator)])
def operator_ship(order_id: str, inp: ShipIn, db: Session = Depends(get_db)):
    """Mark a packed parcel shipped with the carrier and tracking code from its label.

    No locker is involved. The customer's order page shows the tracking, and the handoff
    email carrying it goes out after the commit.
    """
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    try:
        package = ship_order(db, order, carrier=inp.carrier, tracking_code=inp.tracking_code)
        db.commit()
    except OrderError as exc:
        db.rollback()
        raise HTTPException(409, str(exc))
    notify_order(db, order, "handoff")
    paypal_tracking = _push_paypal_tracking(db, order, carrier=inp.carrier, tracking_code=inp.tracking_code)
    view = order_view(db, order)
    return {"order_id": order.id, "order_number": order.order_number, "state": order.state,
            "package_id": package.id, "tracking": view["tracking"], "paypal_tracking": paypal_tracking}


def _push_paypal_tracking(db: Session, order: Order, *, carrier: str, tracking_code: str) -> dict | None:
    """After the parcel left: give PayPal the carrier and the number (seller protection needs
    it). Runs after the commit, so PayPal being down never undoes a shipment; the order-mail
    timer retries what failed (paypal.sync_pending_tracking)."""
    if order.payment_method != "PAYPAL" or not order.paypal_capture_id or order.paypal_tracking_id:
        return None
    try:
        tracker = paypal.push_tracking(db, order, carrier=carrier, tracking_number=tracking_code)
        db.commit()
        return {"pushed": True, "tracker_id": tracker}
    except paypal.PayPalError as exc:
        db.rollback()
        return {"pushed": False, "error": str(exc), "retry": "the order-mail timer retries"}


@router.get("/v1/orders/{order_id}/mail/{kind}/preview", dependencies=[Depends(require_operator)])
def operator_mail_preview(order_id: str, kind: str, format: str = Query(default="html", pattern="^(html|text)$"),
                          db: Session = Depends(get_db)):
    """The email this order produces for `kind`, rendered exactly as it would be sent. Sends nothing."""
    if kind not in MAIL_KINDS:
        raise HTTPException(404, "Unknown mail kind")
    order = db.get(Order, order_id)
    if not order or order.channel != "WEB":
        raise HTTPException(404, "Order not found")
    try:
        content = render_order_mail(db, order, kind)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    if format == "text":
        return PlainTextResponse(f"Subject: {content.subject}\n\n{content.text}")
    return HTMLResponse(content.html.replace("<body", f"<body data-subject=\"{_html_attr(content.subject)}\"", 1))


def _html_attr(value: str) -> str:
    from html import escape
    return escape(value, quote=True)


@router.get("/v1/orders/awaiting-payment", dependencies=[Depends(require_operator)])
def awaiting_payment(db: Session = Depends(get_db)):
    from sqlalchemy import select
    rows = list(db.scalars(select(Order).where(Order.state == "AWAITING_PAYMENT").order_by(Order.created_at.desc()).limit(200)))
    return {"orders": [order_view(db, o) | {"order_id": o.id} for o in rows]}


# ------------------------------------------------------------------ stripe webhook

def _process_stripe_webhook(db: Session, raw: bytes, signature: str, secret: str) -> dict:
    if not verify_stripe_signature(raw, signature, secret):
        raise HTTPException(401, "Invalid Stripe signature")
    try:
        event = json.loads(raw)
    except ValueError:
        raise HTTPException(400, "Invalid JSON")
    try:
        order = apply_stripe_event(db, event)
        db.commit()
    except StorefrontError as exc:
        db.rollback()
        if exc.code == "amount_mismatch":
            record_payment_mismatch(db, exc)
            db.commit()
            raise _err(exc, 400)
        raise _err(exc, 409)
    if order is not None and order.paid_at is not None:
        notify_order(db, order, "paid")
    return {"ok": True, "order_number": order.order_number if order else None, "state": order.state if order else None}


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    raw = await request.body()
    return _process_stripe_webhook(db, raw, request.headers.get("stripe-signature", ""), os.getenv("STRIPE_WEBHOOK_SECRET", ""))


# ------------------------------------------------------------------ PayPal
#
# The storefront's PayPal button (JS SDK v6) calls these two from its createOrder and
# onApprove callbacks; the shopping agent and the MCP checkout use the same two. The buyer
# proves the order with its access key, exactly as on the order page.

@router.post("/v1/storefront/orders/{order_number}/paypal")
def paypal_open(order_number: str, request: Request, email: str | None = None,
                x_order_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    """Create (or reuse) the PayPal order for this unpaid PAYPAL order: {id, status, approve_url}."""
    if not order_limiter.allow(client_address(request)):
        raise HTTPException(429, {"code": "rate_limited", "message": "Too many attempts"})
    try:
        order = _customer_order(db, order_number, x_order_token, email)
        opened = paypal.create_for(db, order)
        db.commit()
    except StorefrontError as exc:
        db.rollback()
        raise _err(exc, 404 if exc.code == "not_found" else 409)
    except paypal.PayPalError as exc:
        db.rollback()
        raise HTTPException(502, {"code": exc.code, "message": str(exc)})
    return opened


@router.post("/v1/storefront/orders/{order_number}/paypal/capture")
def paypal_capture(order_number: str, inp: PayPalCaptureIn, request: Request, email: str | None = None,
                   x_order_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    """Capture the payment the buyer approved in PayPal. The order is paid only on an exact match."""
    if not order_limiter.allow(client_address(request)):
        raise HTTPException(429, {"code": "rate_limited", "message": "Too many attempts"})
    try:
        order = _customer_order(db, order_number, x_order_token, email)
        was_paid = order.paid_at is not None
        paypal.capture_for(db, order, inp.paypal_order_id)
        db.commit()
    except StorefrontError as exc:
        db.rollback()
        if exc.code == "amount_mismatch":
            record_payment_mismatch(db, exc)
            db.commit()
        raise _err(exc, 404 if exc.code == "not_found" else (402 if exc.code == "declined" else 409))
    except paypal.PayPalError as exc:
        db.rollback()
        raise HTTPException(502, {"code": exc.code, "message": str(exc)})
    if order.paid_at is not None and not was_paid:
        notify_order(db, order, "paid")
    return order_view(db, order)


@router.post("/webhooks/paypal")
async def paypal_webhook(request: Request, db: Session = Depends(get_db)):
    raw = await request.body()
    try:
        event = json.loads(raw)
    except ValueError:
        raise HTTPException(400, "Invalid JSON")
    if not paypal.verify_webhook(dict(request.headers), event):
        raise HTTPException(401, "PayPal did not confirm this delivery")
    from ..models import WebhookEvent
    from sqlalchemy import select
    import hashlib
    event_id = str(event.get("id") or "")[:160]
    if event_id and db.scalar(select(WebhookEvent).where(WebhookEvent.source == "paypal", WebhookEvent.external_event_id == event_id)):
        return {"ok": True, "duplicate": True}
    try:
        order = paypal.apply_webhook_event(db, event)
        if event_id:
            db.add(WebhookEvent(source="paypal", external_event_id=event_id, payload_hash=hashlib.sha256(raw).hexdigest()))
        db.commit()
    except StorefrontError as exc:
        db.rollback()
        if exc.code == "amount_mismatch":
            record_payment_mismatch(db, exc)
            db.commit()
        raise _err(exc, 400 if exc.code == "amount_mismatch" else 409)
    except paypal.PayPalError as exc:
        db.rollback()
        raise HTTPException(502, {"code": exc.code, "message": str(exc)})
    if order is not None and order.paid_at is not None and event.get("event_type") in {"PAYMENT.CAPTURE.COMPLETED", "CHECKOUT.ORDER.APPROVED"}:
        notify_order(db, order, "paid")  # one email per order and kind, however many deliveries
    return {"ok": True, "order_number": order.order_number if order else None, "state": order.state if order else None}
