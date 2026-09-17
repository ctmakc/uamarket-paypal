"""Storefront: public catalogue, web orders, payment transitions, Stripe webhook."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.ratelimit import lookup_limiter, order_limiter
from app.services.storefront import verify_stripe_signature


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.setenv("ETRANSFER_EMAIL", "pay@uamarket-fixture.ca")
    # These tests exercise a shop selling its real catalogue; demo orders withhold payment details.
    monkeypatch.setenv("SHOP_CATALOGUE_STATUS", "live")
    monkeypatch.setenv("TAX_RATES_JSON", json.dumps({"ON": 0.13}))
    monkeypatch.setenv("SHIPPING_FLAT_CAD", "12")
    monkeypatch.setenv("SHIPPING_FREE_OVER_CAD", "150")
    order_limiter.reset()
    lookup_limiter.reset()
    app = create_app(f"sqlite:///{tmp_path / 'storefront.db'}", create_schema=True)
    c = TestClient(app)
    r = c.post("/admin/seed-catalog")
    assert r.status_code == 200, r.text
    return c


def _first_in_stock(client, slug):
    """A variant with comfortable stock (in stock and not flagged low) so qty 1-2 orders pass."""
    p = client.get(f"/v1/catalog/products/{slug}").json()
    healthy = [v for v in p["variants"] if v["availability"]["in_stock"] and not v["availability"]["low"]]
    v = healthy[0] if healthy else next(v for v in p["variants"] if v["availability"]["in_stock"])
    return p, v


def _order_payload(lines, **overrides):
    payload = {
        "idempotency_key": f"test-{uuid.uuid4()}",
        "email": "buyer@example.test",
        "name": "Olena Buyer",
        "fulfillment_method": "SHIP",
        "ship_to": {"street1": "1 Main St", "city": "Ottawa", "province": "ON", "postal_code": "k1a0b1"},
        "lines": lines,
    }
    payload.update(overrides)
    return payload


def test_catalog_lists_and_details(client):
    r = client.get("/v1/catalog/products")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 20
    first = data["items"][0]
    assert first["featured"] is True  # featured sort first
    for key in ("slug", "title", "title_uk", "price_from_cad", "origin_label", "maker", "in_stock"):
        assert key in first
    assert "variants" not in first  # summary view

    r = client.get(f"/v1/catalog/products/{first['slug']}")
    assert r.status_code == 200
    detail = r.json()
    assert detail["variants"], "detail must carry variants"
    assert all("availability" in v and set(v["availability"]) == {"in_stock", "low"} for v in detail["variants"])
    assert "related" in detail
    assert client.get("/v1/catalog/products/does-not-exist").status_code == 404

    cols = client.get("/v1/catalog/collections").json()["items"]
    assert sum(c["count"] for c in cols) == data["total"]
    assert client.get("/v1/catalog/products", params={"collection": "heritage"}).json()["total"] >= 4
    assert client.get("/v1/catalog/products", params={"category": "kids"}).json()["total"] >= 2
    assert client.get("/v1/catalog/products", params={"q": "борщ"}).json()["total"] >= 1

    makers = client.get("/v1/catalog/makers").json()["items"]
    assert makers and all(m["product_count"] > 0 for m in makers)
    maker = client.get(f"/v1/catalog/makers/{makers[0]['slug']}").json()
    assert maker["products"]


def test_catalog_never_leaks_warehouse_data(client):
    p = client.get("/v1/catalog/products").json()["items"][0]
    detail = client.get(f"/v1/catalog/products/{p['slug']}").json()
    blob = json.dumps(detail)
    for forbidden in ("A-LANE", "B-BIN", "qty_on_hand", "qty_reserved", "barcode", "location"):
        assert forbidden not in blob


def test_web_order_prices_come_from_database_and_totals_follow_config(client):
    p, v = _first_in_stock(client, "opishnia-mug")
    lines = [{"sku": v["sku"], "qty": 2}]
    quote = client.post("/v1/storefront/quote", json={"lines": lines, "fulfillment_method": "SHIP", "ship_to": {"province": "ON"}}).json()
    assert quote["subtotal_cad"] == round(2 * v["price_cad"], 2)
    assert quote["shipping_cad"] == 12.0
    assert quote["tax_rate"] == 0.13
    assert quote["total_cad"] == round((quote["subtotal_cad"] + 12) * 1.13, 2)

    r = client.post("/v1/storefront/orders", json=_order_payload(lines))
    assert r.status_code == 201, r.text
    order = r.json()
    assert order["order_number"].startswith("UA-")
    assert order["status"]["raw"] == "AWAITING_PAYMENT"
    assert order["totals"]["total_cad"] == quote["total_cad"]
    assert order["lines"][0]["unit_price_cad"] == v["price_cad"]
    assert order["payment"]["method"] == "ETRANSFER"
    assert order["payment"]["recipient_email"] == "pay@uamarket-fixture.ca"
    assert order["payment"]["message"] == order["order_number"]
    assert order["ship_to"]["postal_code"] == "K1A 0B1"

    # Unknown province => no tax line invented; pickup => no shipping
    r = client.post("/v1/storefront/orders", json=_order_payload(lines, fulfillment_method="PICKUP", ship_to=None))
    assert r.status_code == 201
    pick = r.json()["totals"]
    assert pick["shipping_cad"] == 0.0 and pick["tax_rate"] == 0.13  # pickup province ON configured

    r = client.post("/v1/storefront/quote", json={"lines": lines, "fulfillment_method": "SHIP", "ship_to": {"province": "BC"}}).json()
    assert r["tax_cad"] == 0.0 and r["tax_rate"] is None


def test_web_order_is_idempotent_and_refuses_bad_input(client):
    p, v = _first_in_stock(client, "kids-shirt-classic")
    payload = _order_payload([{"sku": v["sku"], "qty": 1}])
    first = client.post("/v1/storefront/orders", json=payload)
    second = client.post("/v1/storefront/orders", json=payload)
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["order_number"] == second.json()["order_number"]
    assert second.json()["duplicate"] is True

    r = client.post("/v1/storefront/orders", json=_order_payload([{"sku": "NOPE-1", "qty": 1}]))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "unknown_sku"

    r = client.post("/v1/storefront/orders", json=_order_payload([{"sku": v["sku"], "qty": 500}]))
    assert r.status_code == 422  # schema bound

    r = client.post("/v1/storefront/orders", json=_order_payload([{"sku": v["sku"], "qty": 1}], ship_to={"street1": "", "city": "", "province": "ON", "postal_code": ""}))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "ship_to"

    r = client.post("/v1/storefront/orders", json=_order_payload([{"sku": v["sku"], "qty": 1}], ship_to={"street1": "x", "city": "y", "province": "ON", "postal_code": "12345"}))
    assert r.status_code == 400

    r = client.post("/v1/storefront/orders", json=_order_payload([{"sku": v["sku"], "qty": 1}], payment_method="STRIPE"))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "payment_method"


def test_web_order_refuses_more_than_stock(client):
    detail = client.get("/v1/catalog/products/motanka-classic").json()
    sold_out = [v for v in detail["variants"] if not v["availability"]["in_stock"]]
    in_stock = [v for v in detail["variants"] if v["availability"]["in_stock"]]
    assert in_stock
    r = client.post("/v1/storefront/orders", json=_order_payload([{"sku": in_stock[0]["sku"], "qty": 20}]))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "out_of_stock"
    if sold_out:
        r = client.post("/v1/storefront/orders", json=_order_payload([{"sku": sold_out[0]["sku"], "qty": 1}]))
        assert r.status_code == 409


def test_status_lookup_requires_matching_email_and_paid_transition(client):
    p, v = _first_in_stock(client, "everyday-linen-shirt-men")
    order = client.post("/v1/storefront/orders", json=_order_payload([{"sku": v["sku"], "qty": 1}])).json()
    num = order["order_number"]
    assert client.get(f"/v1/storefront/orders/{num}", params={"email": "someone@else.test"}).status_code == 404
    ok = client.get(f"/v1/storefront/orders/{num.lower()}", params={"email": "BUYER@example.test"})
    assert ok.status_code == 200 and ok.json()["payment"]["due"] is True

    # dashboard shows the unpaid web order without counting it as work
    dash = client.get("/v1/dashboard").json()
    assert dash["awaiting_payment"] >= 1

    # operator confirms the e-Transfer
    from sqlalchemy import select
    from app.models import Order
    with client.app.state.SessionLocal() as db:
        oid = db.scalar(select(Order.id).where(Order.order_number == num))
    r = client.post(f"/v1/orders/{oid}/mark-paid", json={"reference": "etransfer-123"})
    # Marking paid reserves the goods in the same step: the held stock becomes the order's.
    assert r.status_code == 200 and r.json()["state"] == "PICK_PLANNED"
    again = client.post(f"/v1/orders/{oid}/mark-paid", json={})
    assert again.status_code == 200  # idempotent

    view = client.get(f"/v1/storefront/orders/{num}", params={"email": "buyer@example.test"}).json()
    assert view["status"]["key"] == "paid" and view["payment"]["due"] is False and view["paid_at"]

    # and now the existing warehouse pipeline takes it: reserve -> missions
    r = client.post(f"/v1/orders/{oid}/reserve")
    assert r.status_code == 200 and r.json()["state"] == "PICK_PLANNED"
    assert client.get("/v1/orders/awaiting-payment").json()["orders"] == [] or all(o["order_number"] != num for o in client.get("/v1/orders/awaiting-payment").json()["orders"])

    # cancelling a paid order through the public endpoint is refused
    r = client.post(f"/v1/storefront/orders/{num}/cancel", params={"email": "buyer@example.test"})
    assert r.status_code == 409


def test_public_cancel_of_unpaid_order(client):
    p, v = _first_in_stock(client, "greeting-cards")
    order = client.post("/v1/storefront/orders", json=_order_payload([{"sku": v["sku"], "qty": 1}], fulfillment_method="PICKUP", ship_to=None)).json()
    r = client.post(f"/v1/storefront/orders/{order['order_number']}/cancel", params={"email": "buyer@example.test"})
    assert r.status_code == 200 and r.json()["status"]["key"] == "cancelled"


def test_stripe_signature_and_webhook(client, monkeypatch):
    secret = "whsec_test"
    raw = b'{"id":"evt_1","type":"checkout.session.completed","data":{"object":{"id":"cs_1","payment_status":"paid","client_reference_id":"ORDER_ID","payment_intent":"pi_1","amount_total":AMOUNT,"currency":"cad"}}}'
    ts = int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + raw, hashlib.sha256).hexdigest()
    assert verify_stripe_signature(raw, f"t={ts},v1={sig}", secret)
    assert not verify_stripe_signature(raw, f"t={ts},v1={'0' * 64}", secret)
    assert not verify_stripe_signature(raw, f"t={ts - 10_000},v1={sig}", secret)  # stale
    assert not verify_stripe_signature(raw, "", secret)

    # end-to-end: an unpaid web order becomes PAID from a signed event
    p, v = _first_in_stock(client, "enamel-pin-set")
    order = client.post("/v1/storefront/orders", json=_order_payload([{"sku": v["sku"], "qty": 1}])).json()
    from sqlalchemy import select
    from app.models import Order
    with client.app.state.SessionLocal() as db:
        oid = db.scalar(select(Order.id).where(Order.order_number == order["order_number"]))
    body = raw.replace(b"ORDER_ID", oid.encode()).replace(b"AMOUNT", str(round(order["totals"]["total_cad"] * 100)).encode())
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", secret)
    ts = int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    r = client.post("/webhooks/stripe", content=body, headers={"stripe-signature": f"t={ts},v1={sig}", "content-type": "application/json"})
    assert r.status_code == 200 and r.json()["state"] == "PICK_PLANNED"
    r = client.post("/webhooks/stripe", content=body, headers={"stripe-signature": "t=1,v1=bad"})
    assert r.status_code == 401


def test_order_rate_limit(client):
    p, v = _first_in_stock(client, "opishnia-mug")
    codes = []
    for _ in range(12):
        codes.append(client.post("/v1/storefront/orders", json=_order_payload([{"sku": v["sku"], "qty": 1}])).status_code)
    assert 429 in codes
