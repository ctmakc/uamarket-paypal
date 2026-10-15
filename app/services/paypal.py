"""PayPal for web orders: Orders v2 over REST, no SDK.

What the shop asks of PayPal and what it trusts back:

- An order placed with payment_method PAYPAL gets one PayPal order, built here from the
  shop's own database: every line, the shipping and the named taxes, in CAD. The browser
  never sends a price; the PayPal order carries `custom_id` = the shop order id and
  `invoice_id` = the order number, so a payment can always be traced back.
- The buyer approves in PayPal (JS SDK v6 popup, or the approval link an agent hands
  over). Money moves only on capture, and capture happens here, on the server.
- A capture marks the order paid only when PayPal says COMPLETED and the captured amount
  and currency are exactly this order's total. Anything else is recorded, not believed.
- Webhooks (PAYMENT.CAPTURE.*, CHECKOUT.ORDER.APPROVED) are verified with PayPal's
  verify-webhook-signature API before they touch an order, and are idempotent.
- After the parcel leaves, the carrier and tracking number go back to PayPal (Orders v2
  /track). A cancelled paid order can be refunded through PayPal from the admin.

Settings: PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET, PAYPAL_ENV (sandbox | live, default
sandbox), PAYPAL_WEBHOOK_ID (from the developer dashboard; without it webhooks are refused).
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import threading
import time
from decimal import ROUND_HALF_UP, Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Order, Product, Variant

log = logging.getLogger("uamarket.paypal")

SANDBOX_API = "https://api-m.sandbox.paypal.com"
LIVE_API = "https://api-m.paypal.com"
SANDBOX_SDK = "https://www.sandbox.paypal.com/web-sdk/v6/core"
LIVE_SDK = "https://www.paypal.com/web-sdk/v6/core"

# PayPal's own names for the carriers a Canadian shop hands parcels to. Anything else goes
# as OTHER with the name the operator typed.
CARRIERS = {
    "canada post": "CANADA_POST", "canadapost": "CANADA_POST", "postes canada": "CANADA_POST",
    "purolator": "PUROLATOR", "ups": "UPS", "fedex": "FEDEX", "dhl": "DHL", "canpar": "CANPAR",
    "usps": "USPS", "ukrposhta": "UKRPOSHTA", "nova poshta": "NOVA_POSHTA",
}


class PayPalError(RuntimeError):
    def __init__(self, message: str, *, code: str = "paypal", status: int | None = None, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.status = status
        self.details = details or {}


# --------------------------------------------------------------------------- settings

def environment() -> str:
    return "live" if (os.getenv("PAYPAL_ENV") or "").strip().lower() == "live" else "sandbox"


def sandbox() -> bool:
    return environment() == "sandbox"


def client_id() -> str:
    return (os.getenv("PAYPAL_CLIENT_ID") or "").strip()


def _secret() -> str:
    return (os.getenv("PAYPAL_CLIENT_SECRET") or "").strip()


def webhook_id() -> str:
    return (os.getenv("PAYPAL_WEBHOOK_ID") or "").strip()


def configured() -> bool:
    return bool(client_id() and _secret())


def api_base() -> str:
    override = (os.getenv("PAYPAL_API_BASE") or "").strip().rstrip("/")
    if override:
        return override
    return SANDBOX_API if sandbox() else LIVE_API


def sdk_url() -> str:
    return SANDBOX_SDK if sandbox() else LIVE_SDK


def public_config() -> dict | None:
    """What the browser needs for the JS SDK v6 button: the client id is browser-safe."""
    if not configured():
        return None
    return {"client_id": client_id(), "env": environment(), "sdk_url": sdk_url(), "currency": "CAD"}


# --------------------------------------------------------------------------- transport

_token_lock = threading.Lock()
_token: dict = {"value": None, "expires": 0.0, "key": None}

# Tests swap this for an httpx.MockTransport.
TRANSPORT: httpx.BaseTransport | None = None


def _client() -> httpx.Client:
    return httpx.Client(base_url=api_base(), timeout=25, transport=TRANSPORT)


def access_token() -> str:
    """A client-credentials token, cached until a minute before PayPal says it expires."""
    key = (api_base(), client_id())
    with _token_lock:
        if _token["value"] and _token["key"] == key and _token["expires"] > time.time() + 60:
            return _token["value"]
        if not configured():
            raise PayPalError("PayPal is not configured", code="not_configured")
        with _client() as http:
            resp = http.post("/v1/oauth2/token", data={"grant_type": "client_credentials"},
                             auth=(client_id(), _secret()), headers={"Accept": "application/json"})
        if resp.status_code >= 300:
            raise PayPalError("PayPal refused the shop's credentials", code="auth", status=resp.status_code)
        body = resp.json()
        _token.update(value=body["access_token"], expires=time.time() + int(body.get("expires_in", 300)), key=key)
        return _token["value"]


def reset_token_cache() -> None:
    with _token_lock:
        _token.update(value=None, expires=0.0, key=None)


def call(method: str, path: str, *, body: dict | None = None, request_id: str | None = None,
         prefer: str = "return=representation") -> tuple[int, dict]:
    """One PayPal REST call. Returns (status, json). Raises PayPalError on transport failure."""
    headers = {"Authorization": f"Bearer {access_token()}", "Content-Type": "application/json", "Prefer": prefer}
    if request_id:
        headers["PayPal-Request-Id"] = request_id
    try:
        with _client() as http:
            resp = http.request(method, path, json=body, headers=headers)
    except httpx.HTTPError as exc:
        raise PayPalError(f"PayPal could not be reached: {exc.__class__.__name__}", code="unreachable") from exc
    try:
        data = resp.json() if resp.content else {}
    except ValueError:
        data = {"raw": resp.text[:500]}
    if resp.status_code >= 400:
        log.warning("paypal %s %s -> %s %s", method, path, resp.status_code, json.dumps(data)[:800])
    return resp.status_code, data


def _issue(data: dict) -> str | None:
    details = data.get("details") or []
    if details and isinstance(details, list):
        return details[0].get("issue")
    return data.get("name")


# --------------------------------------------------------------------------- order payload

def _money(value) -> str:
    return str(Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def build_order_request(db: Session, order: Order, *, return_url: str | None = None, cancel_url: str | None = None) -> dict:
    """The Orders v2 create body for this shop order, priced from the database only.

    PayPal checks that items add up to item_total and that item_total + shipping + tax
    equal the amount; the order's frozen totals are re-added here line by line, and a shop
    order whose stored totals do not add up is refused rather than sent with a fudge.
    """
    items = []
    item_total = Decimal("0.00")
    for line in order.lines:
        v = db.get(Variant, line.variant_id)
        product = db.get(Product, v.product_id) if v and v.product_id else None
        name = product.title if product else (v.name if v else "Item")
        if v and v.option_label:
            name = f"{name} ({v.option_label})"
        unit = Decimal(_money(line.unit_price_cad))
        item_total += unit * line.qty
        item = {
            "name": name[:127],
            "quantity": str(line.qty),
            "unit_amount": {"currency_code": "CAD", "value": str(unit)},
            "category": "PHYSICAL_GOODS",
        }
        if v and v.sku:
            item["sku"] = v.sku[:127]
        items.append(item)
    shipping = Decimal(_money(order.shipping_cad))
    tax = Decimal(_money(order.tax_cad))
    total = Decimal(_money(order.gross_amount_cad))
    if item_total + shipping + tax != total:
        raise PayPalError("The order's stored totals do not add up; refusing to send it to PayPal", code="totals",
                          details={"items": str(item_total), "shipping": str(shipping), "tax": str(tax), "total": str(total)})
    unit = {
        "reference_id": order.order_number or order.id,
        "custom_id": order.id,
        # PayPal refuses a second order with an invoice id it has already seen paid; the
        # suffix keeps a rebuilt demo database from colliding with an earlier run.
        "invoice_id": f"{order.order_number}-{order.id[:6]}",
        "description": f"UA Market order {order.order_number}"[:127],
        "amount": {
            "currency_code": "CAD", "value": str(total),
            "breakdown": {
                "item_total": {"currency_code": "CAD", "value": str(item_total)},
                "shipping": {"currency_code": "CAD", "value": str(shipping)},
                "tax_total": {"currency_code": "CAD", "value": str(tax)},
            },
        },
        "items": items,
    }
    ship = json.loads(order.ship_to_json or "{}") if order.fulfillment_method == "SHIP" else {}
    if ship:
        unit["shipping"] = {
            "type": "SHIPPING",
            "name": {"full_name": (ship.get("name") or order.customer_name or "")[:300]},
            "address": {k: v for k, v in {
                "address_line_1": ship.get("street1"), "address_line_2": ship.get("street2"),
                "admin_area_2": ship.get("city"), "admin_area_1": ship.get("province"),
                "postal_code": ship.get("postal_code"), "country_code": ship.get("country") or "CA",
            }.items() if v},
        }
    experience = {
        "brand_name": "UA Market",
        "locale": "uk-UA" if (order.locale or "en") == "uk" else "en-CA",
        # The address was given at checkout and the tax was computed for its province, so
        # the buyer may not swap it inside PayPal. Pickup orders carry no address at all.
        "shipping_preference": "SET_PROVIDED_ADDRESS" if ship else "NO_SHIPPING",
        "user_action": "PAY_NOW",
    }
    if return_url:
        experience["return_url"] = return_url
    if cancel_url:
        experience["cancel_url"] = cancel_url
    body = {
        "intent": "CAPTURE",
        "purchase_units": [unit],
        "payment_source": {"paypal": {"experience_context": experience}},
    }
    if order.customer_email:
        body["payment_source"]["paypal"]["email_address"] = order.customer_email
    return body


# --------------------------------------------------------------------------- lifecycle

def _approve_link(data: dict) -> str | None:
    for link in data.get("links") or []:
        if link.get("rel") in {"payer-action", "approve"}:
            return link.get("href")
    return None


def create_for(db: Session, order: Order) -> dict:
    """Open (or reuse) the PayPal order for an unpaid PAYPAL shop order.

    Returns {"id", "status", "approve_url"}. Stock is held for the order before PayPal is
    asked, the same rule card sessions follow: nobody approves a payment for goods the shop
    no longer has.
    """
    from . import storefront as sf  # storefront imports this module; import late

    if not configured():
        raise sf.StorefrontError("PayPal is not configured", code="payment_method")
    if order.payment_method != "PAYPAL":
        raise sf.StorefrontError("This order is not paid with PayPal", code="payment_method")
    if order.state != "AWAITING_PAYMENT":
        raise sf.StorefrontError(f"Order is {order.state}, not awaiting payment", code="state")
    if order.is_demo and not sandbox():
        # Demonstration goods are never sold for real money, PayPal included.
        raise sf.StorefrontError("Demo orders are paid in the PayPal sandbox only", code="payment_method")
    sf.ensure_stock_for_payment(db, order)

    if order.paypal_order_id and order.paypal_status in {"CREATED", "PAYER_ACTION_REQUIRED", "APPROVED"}:
        status, data = call("GET", f"/v2/checkout/orders/{order.paypal_order_id}")
        if status == 200 and data.get("status") in {"CREATED", "PAYER_ACTION_REQUIRED", "APPROVED"}:
            amount = ((data.get("purchase_units") or [{}])[0].get("amount") or {})
            if amount.get("value") == _money(order.gross_amount_cad) and amount.get("currency_code") == "CAD":
                order.paypal_status = data["status"]
                return {"id": data["id"], "status": data["status"], "approve_url": _approve_link(data)}

    body = build_order_request(
        db, order,
        return_url=sf.order_page_return_url(order, paid=False) + "&paypal=return",
        cancel_url=sf.order_page_return_url(order, paid=False) + "&paypal=cancel",
    )
    status, data = call("POST", "/v2/checkout/orders", body=body, request_id=f"create-{order.id}-{secrets.token_hex(4)}")
    if status >= 300 or not data.get("id"):
        raise sf.StorefrontError("PayPal refused to open the payment", code="paypal",
                                 details={"status": status, "issue": _issue(data)})
    order.paypal_order_id = data["id"]
    order.paypal_status = data.get("status") or "CREATED"
    order.checkout_session_id = data["id"]
    return {"id": data["id"], "status": order.paypal_status, "approve_url": _approve_link(data)}


def _capture_of(data: dict) -> dict:
    units = data.get("purchase_units") or []
    caps = ((units[0].get("payments") or {}).get("captures") or []) if units else []
    return caps[0] if caps else {}


def apply_capture(db: Session, order: Order, capture: dict) -> Order:
    """Record what PayPal says about this order's capture, believing only an exact match."""
    from . import storefront as sf

    status = capture.get("status")
    amount = capture.get("amount") or {}
    if capture.get("id"):
        order.paypal_capture_id = capture["id"]
    if status:
        order.paypal_status = status
    if status != "COMPLETED":
        if status in {"DECLINED", "FAILED"}:
            raise sf.StorefrontError("PayPal declined the payment", code="declined", details={"status": status})
        return order  # PENDING: the webhook finishes it when PayPal does
    if amount.get("currency_code") != "CAD" or amount.get("value") != _money(order.gross_amount_cad):
        raise sf.StorefrontError(
            "Paid amount does not match the order", code="amount_mismatch",
            details={"order_number": order.order_number, "expected": _money(order.gross_amount_cad),
                     "amount": amount.get("value"), "currency": amount.get("currency_code"),
                     "capture": capture.get("id"), "provider": "PAYPAL"},
        )
    return sf.mark_paid(db, order, reference=capture.get("id"), method="PAYPAL")


def capture_for(db: Session, order: Order, paypal_order_id: str) -> Order:
    """Capture the approved PayPal order of this shop order. Safe to repeat."""
    from . import storefront as sf

    if not paypal_order_id or paypal_order_id != order.paypal_order_id:
        raise sf.StorefrontError("That PayPal payment does not belong to this order", code="payment_method")
    if order.paid_at is not None:
        return order
    if order.state != "AWAITING_PAYMENT":
        raise sf.StorefrontError(f"Order is {order.state}, not awaiting payment", code="state")
    status, data = call("POST", f"/v2/checkout/orders/{paypal_order_id}/capture", request_id=f"capture-{order.id}-{paypal_order_id}")
    if status == 422 and _issue(data) == "ORDER_ALREADY_CAPTURED":
        status, data = call("GET", f"/v2/checkout/orders/{paypal_order_id}")
    if status == 422 and _issue(data) in {"INSTRUMENT_DECLINED", "PAYER_ACTION_REQUIRED"}:
        # The buyer can pick another funding source in the same PayPal window.
        raise sf.StorefrontError("PayPal declined that funding source; choose another in PayPal", code="declined",
                                 details={"issue": _issue(data)})
    if status >= 300:
        raise sf.StorefrontError("PayPal could not capture the payment", code="paypal",
                                 details={"status": status, "issue": _issue(data)})
    capture = _capture_of(data)
    if not capture:
        order.paypal_status = data.get("status") or order.paypal_status
        raise sf.StorefrontError("PayPal returned no capture", code="paypal", details={"status": data.get("status")})
    return apply_capture(db, order, capture)


def refresh(db: Session, order: Order) -> dict:
    """PayPal's current view of the order, for the admin. Read only."""
    if not order.paypal_order_id:
        return {}
    status, data = call("GET", f"/v2/checkout/orders/{order.paypal_order_id}")
    if status != 200:
        return {"error": _issue(data) or status}
    capture = _capture_of(data)
    return {
        "id": data.get("id"), "status": data.get("status"),
        "capture": {"id": capture.get("id"), "status": capture.get("status"), "amount": capture.get("amount")} if capture else None,
        "payer": {"country": ((data.get("payer") or {}).get("address") or {}).get("country_code")},
    }


# --------------------------------------------------------------------------- after payment

def carrier_code(carrier: str) -> tuple[str, str | None]:
    name = (carrier or "").strip()
    code = CARRIERS.get(name.lower())
    return (code, None) if code else ("OTHER", name[:64] or "Other")


def push_tracking(db: Session, order: Order, *, carrier: str, tracking_number: str) -> str:
    """Tell PayPal the parcel left (Orders v2 /track). Returns PayPal's tracker id."""
    if not (order.paypal_order_id and order.paypal_capture_id):
        raise PayPalError("This order was not captured through PayPal", code="not_paypal")
    code, other = carrier_code(carrier)
    body = {"capture_id": order.paypal_capture_id, "tracking_number": tracking_number[:64], "carrier": code,
            "notify_payer": False}
    if other:
        body["carrier_name_other"] = other
    status, data = call("POST", f"/v2/checkout/orders/{order.paypal_order_id}/track", body=body,
                        request_id=f"track-{order.id}-{tracking_number[:40]}")
    if status >= 300:
        raise PayPalError("PayPal refused the tracking number", code="tracking", status=status, details={"issue": _issue(data)})
    trackers = ((data.get("purchase_units") or [{}])[0].get("shipping") or {}).get("trackers") or []
    tracker_id = trackers[-1].get("id") if trackers else f"{order.paypal_capture_id}-{tracking_number}"
    order.paypal_tracking_id = tracker_id
    return tracker_id


def refund(db: Session, order: Order, *, note: str | None = None) -> dict:
    """Refund the whole capture of a paid PayPal order (admin, after a cancellation)."""
    if not order.paypal_capture_id:
        raise PayPalError("This order has no PayPal capture to refund", code="not_paypal")
    if order.paypal_refund_id:
        return {"id": order.paypal_refund_id, "status": order.paypal_status}
    body = {"amount": {"currency_code": "CAD", "value": _money(order.gross_amount_cad)},
            "invoice_id": f"{order.order_number}-{order.id[:6]}-R"}
    if note:
        body["note_to_payer"] = note[:255]
    status, data = call("POST", f"/v2/payments/captures/{order.paypal_capture_id}/refund", body=body,
                        request_id=f"refund-{order.id}")
    if status >= 300:
        raise PayPalError("PayPal refused the refund", code="refund", status=status, details={"issue": _issue(data)})
    order.paypal_refund_id = data.get("id")
    order.paypal_status = "REFUNDED" if data.get("status") == "COMPLETED" else f"REFUND_{data.get('status')}"
    return {"id": data.get("id"), "status": data.get("status")}


# --------------------------------------------------------------------------- webhooks

def verify_webhook(headers: dict, event: dict) -> bool:
    """Ask PayPal whether this delivery is genuine (verify-webhook-signature)."""
    wid = webhook_id()
    if not wid or not configured():
        return False
    h = {k.lower(): v for k, v in headers.items()}
    needed = ("paypal-auth-algo", "paypal-cert-url", "paypal-transmission-id", "paypal-transmission-sig",
              "paypal-transmission-time")
    if not all(h.get(k) for k in needed):
        return False
    body = {
        "auth_algo": h["paypal-auth-algo"], "cert_url": h["paypal-cert-url"],
        "transmission_id": h["paypal-transmission-id"], "transmission_sig": h["paypal-transmission-sig"],
        "transmission_time": h["paypal-transmission-time"], "webhook_id": wid, "webhook_event": event,
    }
    status, data = call("POST", "/v1/notifications/verify-webhook-signature", body=body)
    return status == 200 and data.get("verification_status") == "SUCCESS"


WEBHOOK_EVENTS = {
    "CHECKOUT.ORDER.APPROVED", "PAYMENT.CAPTURE.COMPLETED", "PAYMENT.CAPTURE.PENDING", "PAYMENT.CAPTURE.DENIED",
    "PAYMENT.CAPTURE.REFUNDED", "PAYMENT.CAPTURE.REVERSED",
}


def _order_for_resource(db: Session, resource: dict) -> Order | None:
    custom = resource.get("custom_id")
    if not custom:
        units = resource.get("purchase_units") or []
        custom = units[0].get("custom_id") if units else None
    order = db.get(Order, custom) if custom else None
    if order is None and resource.get("id"):
        order = db.scalar(select(Order).where(
            (Order.paypal_order_id == resource["id"]) | (Order.paypal_capture_id == resource["id"])))
    if order is None:
        related = ((resource.get("supplementary_data") or {}).get("related_ids") or {}).get("order_id")
        if related:
            order = db.scalar(select(Order).where(Order.paypal_order_id == related))
    return order if order is not None and order.channel == "WEB" else None


def apply_webhook_event(db: Session, event: dict) -> Order | None:
    """Apply one verified PayPal event. Unknown events and foreign orders are ignored."""
    from . import storefront as sf
    from .orders import open_exception

    kind = event.get("event_type")
    if kind not in WEBHOOK_EVENTS:
        return None
    resource = event.get("resource") or {}
    order = _order_for_resource(db, resource)
    if order is None:
        return None
    if kind == "CHECKOUT.ORDER.APPROVED":
        # The buyer approved and closed the window before the page captured: capture here.
        if order.paid_at is None and order.state == "AWAITING_PAYMENT" and resource.get("id") == order.paypal_order_id:
            return capture_for(db, order, resource["id"])
        return order
    if kind in {"PAYMENT.CAPTURE.COMPLETED", "PAYMENT.CAPTURE.PENDING"}:
        if order.paid_at is not None:
            return order
        if order.state != "AWAITING_PAYMENT":
            return order
        return apply_capture(db, order, resource)
    order.paypal_status = {"PAYMENT.CAPTURE.DENIED": "DENIED", "PAYMENT.CAPTURE.REFUNDED": "REFUNDED",
                           "PAYMENT.CAPTURE.REVERSED": "REVERSED"}[kind]
    if kind in {"PAYMENT.CAPTURE.DENIED", "PAYMENT.CAPTURE.REVERSED"} and order.paid_at is not None:
        open_exception(db, kind=f"PAYPAL_{order.paypal_status}", reference_type="ORDER", reference_id=order.id,
                       details=json.dumps({"summary": f"PayPal reports the payment {order.paypal_status.lower()}. "
                                                      "Hold the parcel and check the PayPal dashboard.",
                                           "order_number": order.order_number, "capture": resource.get("id")}))
    return order


# --------------------------------------------------------------------------- tracking sweep

def sync_pending_tracking(db: Session, *, limit: int = 20) -> int:
    """Push tracking for shipped PayPal orders PayPal has not heard about yet (timer retry)."""
    from ..models import Package, ShipmentRecord
    from .orders import open_exception

    if not configured():
        return 0
    rows = list(db.scalars(select(Order).where(
        Order.payment_method == "PAYPAL", Order.state == "HANDOFF_COMPLETE", Order.paypal_capture_id.is_not(None),
        Order.paypal_tracking_id.is_(None)).limit(limit)))
    done = 0
    for order in rows:
        package = db.scalar(select(Package).where(Package.order_id == order.id))
        record = db.scalar(select(ShipmentRecord).where(ShipmentRecord.package_id == package.id)) if package else None
        if not record or not record.tracking_code:
            continue
        try:
            push_tracking(db, order, carrier=record.carrier or "Other", tracking_number=record.tracking_code)
            done += 1
        except PayPalError as exc:
            open_exception(db, kind="PAYPAL_TRACKING_FAILED", reference_type="ORDER", reference_id=order.id,
                           details=json.dumps({"summary": "PayPal did not take the tracking number; the timer retries.",
                                               "order_number": order.order_number, "error": str(exc),
                                               **exc.details}))
    return done
