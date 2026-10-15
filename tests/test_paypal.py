"""PayPal Orders v2 for web orders, the PayPal webhook, and the two agents' guard rails.

PayPal itself is replaced by an httpx.MockTransport that behaves like the sandbox for the
calls the shop makes (token, create, get, capture, track, refund, verify-webhook-signature).
The live sandbox run is recorded in docs/hackathon/PAYPAL.md.
"""
from __future__ import annotations

import json
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.models import ExceptionRecord, Order, Variant
from app.services import llm, paypal
from app.services.ratelimit import lookup_limiter, order_limiter
from app.services.storefront import ConfigurationError

SHOP_ENV = (
    "PAYMENT_PROVIDER", "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "ETRANSFER_EMAIL", "SHOP_CONTACT_EMAIL",
    "SHOP_CATALOGUE_STATUS", "WEB_INDEXABLE", "PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET", "PAYPAL_ENV", "PAYPAL_WEBHOOK_ID",
    "AI_API_KEY", "AI_BASE_URL", "AI_MODEL",
)
BUYER = "buyer@example.test"


class FakePayPal:
    """Just enough of the PayPal sandbox: orders, capture, track, refund, webhook verification."""

    def __init__(self):
        self.orders: dict[str, dict] = {}
        self.requests: list[tuple[str, str, dict]] = []
        self.capture_amount: str | None = None  # force a wrong captured amount
        self.capture_status = "COMPLETED"
        self.verify = "SUCCESS"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = json.loads(request.content or b"{}") if request.headers.get("content-type", "").startswith("application/json") else {}
        self.requests.append((request.method, path, body))
        if path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "A21-test", "expires_in": 32400})
        if path == "/v2/checkout/orders" and request.method == "POST":
            oid = uuid.uuid4().hex[:17].upper()
            unit = body["purchase_units"][0]
            self.orders[oid] = {"id": oid, "status": "PAYER_ACTION_REQUIRED", "purchase_units": [unit], "body": body}
            return httpx.Response(200, json={"id": oid, "status": "PAYER_ACTION_REQUIRED", "links": [
                {"rel": "payer-action", "href": f"https://www.sandbox.paypal.com/checkoutnow?token={oid}"}]})
        if path.startswith("/v2/checkout/orders/"):
            parts = path.split("/")
            oid = parts[4]
            order = self.orders.get(oid)
            if order is None:
                return httpx.Response(404, json={"name": "RESOURCE_NOT_FOUND"})
            unit = order["purchase_units"][0]
            if len(parts) == 5:
                return httpx.Response(200, json={"id": oid, "status": order["status"], "purchase_units": [unit]})
            if parts[5] == "capture":
                if order["status"] == "COMPLETED":
                    return httpx.Response(422, json={"name": "UNPROCESSABLE_ENTITY", "details": [{"issue": "ORDER_ALREADY_CAPTURED"}]})
                order["status"] = "COMPLETED"
                cap = {"id": "CAP" + oid[:14], "status": self.capture_status, "custom_id": unit["custom_id"],
                       "amount": {"currency_code": "CAD", "value": self.capture_amount or unit["amount"]["value"]}}
                unit["payments"] = {"captures": [cap]}
                return httpx.Response(201, json={"id": oid, "status": "COMPLETED", "purchase_units": [unit]})
            if parts[5] == "track":
                tracker = {"id": f"{body['capture_id']}-{body['tracking_number']}", "status": "SHIPPED"}
                unit.setdefault("shipping", {}).setdefault("trackers", []).append(tracker)
                return httpx.Response(201, json={"id": oid, "purchase_units": [unit]})
        if path.startswith("/v2/payments/captures/") and path.endswith("/refund"):
            return httpx.Response(201, json={"id": "REF" + uuid.uuid4().hex[:14].upper(), "status": "COMPLETED"})
        if path == "/v1/notifications/verify-webhook-signature":
            return httpx.Response(200, json={"verification_status": self.verify})
        return httpx.Response(404, json={"name": "NOT_FOUND", "path": path})

    def approve(self, oid: str):
        self.orders[oid]["status"] = "APPROVED"


@pytest.fixture()
def env(monkeypatch):
    for key in SHOP_ENV:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("WEB_BASE_URL", "http://localhost:3000")
    monkeypatch.setenv("TAX_RATES_JSON", json.dumps({"ON": 0.13}))
    order_limiter.reset()
    lookup_limiter.reset()
    paypal.reset_token_cache()
    return monkeypatch


@pytest.fixture()
def pp(env, monkeypatch):
    fake = FakePayPal()
    monkeypatch.setattr(paypal, "TRANSPORT", httpx.MockTransport(fake))
    env.setenv("PAYPAL_CLIENT_ID", "test-client")
    env.setenv("PAYPAL_CLIENT_SECRET", "test-secret")
    env.setenv("PAYPAL_ENV", "sandbox")
    env.setenv("PAYPAL_WEBHOOK_ID", "WH-TEST")
    return fake


@pytest.fixture()
def shop(pp, tmp_path):
    client = TestClient(create_app(f"sqlite:///{tmp_path / f'pp-{uuid.uuid4().hex[:6]}.db'}", create_schema=True))
    assert client.post("/admin/seed-catalog").status_code == 200
    return client


def _sku(client, slug="opishnia-mug") -> str:
    product = client.get(f"/v1/catalog/products/{slug}").json()
    return next(v["sku"] for v in product["variants"] if v["availability"]["in_stock"])


def _place(client, lines, **extra) -> dict:
    body = {"idempotency_key": f"pp-{uuid.uuid4()}", "email": BUYER, "name": "Olena Buyer", "fulfillment_method": "SHIP",
            "ship_to": {"street1": "1 Main St", "city": "Kanata", "province": "ON", "postal_code": "K2K 1X1"},
            "payment_method": "PAYPAL", "lines": lines, "terms_accepted": True}
    body.update(extra)
    r = client.post("/v1/storefront/orders", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _order(client, number) -> Order:
    with client.app.state.SessionLocal() as db:
        return db.scalar(select(Order).where(Order.order_number == number))


def _open(client, order) -> dict:
    r = client.post(f"/v1/storefront/orders/{order['order_number']}/paypal", headers={"x-order-token": order["access_token"]})
    assert r.status_code == 200, r.text
    return r.json()


def _capture(client, order, ppid):
    return client.post(f"/v1/storefront/orders/{order['order_number']}/paypal/capture",
                       headers={"x-order-token": order["access_token"]}, json={"paypal_order_id": ppid})


# ------------------------------------------------------------------ configuration

def test_paypal_is_offered_first_and_its_sdk_settings_are_public(shop):
    cfg = shop.get("/v1/storefront/config").json()
    assert cfg["payment_methods"][0] == "PAYPAL"
    assert cfg["paypal"] == {"client_id": "test-client", "env": "sandbox", "currency": "CAD",
                             "sdk_url": "https://www.sandbox.paypal.com/web-sdk/v6/core"}
    assert "test-secret" not in json.dumps(cfg)
    assert any(p["name"] == "PayPal (sandbox)" for p in cfg["processors"])


def test_sandbox_paypal_is_refused_on_a_live_catalogue(pp, monkeypatch, tmp_path):
    monkeypatch.setenv("SHOP_CATALOGUE_STATUS", "live")
    with pytest.raises(ConfigurationError):
        create_app(f"sqlite:///{tmp_path / 'live.db'}", create_schema=True)


def test_without_credentials_there_is_no_paypal(env, tmp_path):
    client = TestClient(create_app(f"sqlite:///{tmp_path / 'none.db'}", create_schema=True))
    cfg = client.get("/v1/storefront/config").json()
    assert "PAYPAL" not in cfg["payment_methods"] and cfg["paypal"] is None


# ------------------------------------------------------------------ the order body

def test_paypal_order_is_priced_from_the_database_with_items_shipping_and_tax(shop, pp):
    order = _place(shop, [{"sku": _sku(shop, "kosiv-nyzynka-blouse"), "qty": 1}, {"sku": _sku(shop), "qty": 1}])
    opened = _open(shop, order)
    assert opened["approve_url"].endswith(opened["id"])
    body = pp.orders[opened["id"]]["body"]
    unit = body["purchase_units"][0]
    total = unit["amount"]
    br = total["breakdown"]
    items = sum(float(i["unit_amount"]["value"]) * int(i["quantity"]) for i in unit["items"])
    assert round(items, 2) == float(br["item_total"]["value"])
    assert round(float(br["item_total"]["value"]) + float(br["shipping"]["value"]) + float(br["tax_total"]["value"]), 2) == float(total["value"])
    assert total["value"] == f"{order['totals']['total_cad']:.2f}" and total["currency_code"] == "CAD"
    assert unit["custom_id"] == _order(shop, order["order_number"]).id
    assert unit["invoice_id"].startswith(order["order_number"])
    assert unit["shipping"]["address"]["admin_area_1"] == "ON" and unit["shipping"]["address"]["country_code"] == "CA"
    ctx = body["payment_source"]["paypal"]["experience_context"]
    assert ctx["shipping_preference"] == "SET_PROVIDED_ADDRESS" and ctx["user_action"] == "PAY_NOW"
    # The order stays unpaid until a capture: opening PayPal moves no money.
    assert _order(shop, order["order_number"]).state == "AWAITING_PAYMENT"


def test_a_second_open_reuses_the_live_paypal_order(shop, pp):
    order = _place(shop, [{"sku": _sku(shop), "qty": 1}])
    first = _open(shop, order)
    second = _open(shop, order)
    assert first["id"] == second["id"]
    assert sum(1 for m, p, _ in pp.requests if m == "POST" and p == "/v2/checkout/orders") == 1


def test_opening_needs_the_order_key(shop):
    order = _place(shop, [{"sku": _sku(shop), "qty": 1}])
    r = shop.post(f"/v1/storefront/orders/{order['order_number']}/paypal", headers={"x-order-token": "nope-" + "x" * 30})
    assert r.status_code == 404


# ------------------------------------------------------------------ capture

def test_capture_marks_the_order_paid_and_reserves_it(shop, pp):
    order = _place(shop, [{"sku": _sku(shop), "qty": 1}])
    opened = _open(shop, order)
    pp.approve(opened["id"])
    r = _capture(shop, order, opened["id"])
    assert r.status_code == 200, r.text
    view = r.json()
    assert view["paid_at"] and view["status"]["key"] == "paid"
    assert view["payment"]["paypal"]["capture_id"].startswith("CAP")
    o = _order(shop, order["order_number"])
    assert o.payment_method == "PAYPAL" and o.paypal_status == "COMPLETED" and o.payment_ref == o.paypal_capture_id
    # A repeat (double click, a retried request) is harmless.
    again = _capture(shop, order, opened["id"])
    assert again.status_code == 200 and again.json()["paid_at"][:26] == view["paid_at"][:26]


def test_capture_of_someone_elses_paypal_order_is_refused(shop, pp):
    a = _place(shop, [{"sku": _sku(shop), "qty": 1}])
    b = _place(shop, [{"sku": _sku(shop), "qty": 1}])
    pa = _open(shop, a)
    _open(shop, b)
    r = _capture(shop, b, pa["id"])
    assert r.status_code == 409
    assert _order(shop, b["order_number"]).paid_at is None


def test_a_capture_for_the_wrong_amount_is_not_believed(shop, pp):
    order = _place(shop, [{"sku": _sku(shop), "qty": 1}])
    opened = _open(shop, order)
    pp.capture_amount = "1.00"
    r = _capture(shop, order, opened["id"])
    assert r.status_code == 409 and r.json()["detail"]["code"] == "amount_mismatch"
    assert _order(shop, order["order_number"]).paid_at is None
    with shop.app.state.SessionLocal() as db:
        assert db.scalar(select(ExceptionRecord).where(ExceptionRecord.kind == "PAYMENT_AMOUNT_MISMATCH"))


def test_a_pending_capture_leaves_the_order_unpaid(shop, pp):
    order = _place(shop, [{"sku": _sku(shop), "qty": 1}])
    opened = _open(shop, order)
    pp.capture_status = "PENDING"
    r = _capture(shop, order, opened["id"])
    assert r.status_code == 200 and r.json()["paid_at"] is None
    assert _order(shop, order["order_number"]).paypal_status == "PENDING"


# ------------------------------------------------------------------ webhook

def _hook(client, event, *, headers=True):
    h = {"paypal-auth-algo": "SHA256withRSA", "paypal-cert-url": "https://api.sandbox.paypal.com/cert",
         "paypal-transmission-id": str(uuid.uuid4()), "paypal-transmission-sig": "sig", "paypal-transmission-time": "2026-10-15T00:00:00Z"} if headers else {}
    return client.post("/webhooks/paypal", content=json.dumps(event), headers={"content-type": "application/json", **h})


def test_webhook_needs_paypals_confirmation(shop, pp):
    order = _place(shop, [{"sku": _sku(shop), "qty": 1}])
    opened = _open(shop, order)
    event = {"id": "WH-1", "event_type": "CHECKOUT.ORDER.APPROVED", "resource": {"id": opened["id"]}}
    assert _hook(shop, event, headers=False).status_code == 401
    pp.verify = "FAILURE"
    assert _hook(shop, event).status_code == 401
    assert _order(shop, order["order_number"]).paid_at is None


def test_approved_webhook_captures_when_the_buyer_closed_the_page(shop, pp):
    order = _place(shop, [{"sku": _sku(shop), "qty": 1}])
    opened = _open(shop, order)
    pp.approve(opened["id"])
    event = {"id": "WH-2", "event_type": "CHECKOUT.ORDER.APPROVED", "resource": {"id": opened["id"], "purchase_units": [{"custom_id": _order(shop, order["order_number"]).id}]}}
    r = _hook(shop, event)
    assert r.status_code == 200, r.text
    assert _order(shop, order["order_number"]).paid_at is not None
    assert _hook(shop, event).json().get("duplicate") is True


def test_capture_completed_webhook_pays_a_pending_order(shop, pp):
    order = _place(shop, [{"sku": _sku(shop), "qty": 1}])
    opened = _open(shop, order)
    pp.capture_status = "PENDING"
    _capture(shop, order, opened["id"])
    o = _order(shop, order["order_number"])
    event = {"id": "WH-3", "event_type": "PAYMENT.CAPTURE.COMPLETED", "resource": {
        "id": o.paypal_capture_id, "status": "COMPLETED", "custom_id": o.id,
        "amount": {"currency_code": "CAD", "value": f"{order['totals']['total_cad']:.2f}"}}}
    assert _hook(shop, event).status_code == 200
    assert _order(shop, order["order_number"]).paid_at is not None


# ------------------------------------------------------------------ after payment: tracking and refund

def _paid(shop, pp, qty=1):
    order = _place(shop, [{"sku": _sku(shop), "qty": qty}])
    opened = _open(shop, order)
    pp.approve(opened["id"])
    assert _capture(shop, order, opened["id"]).status_code == 200
    return order, _order(shop, order["order_number"])


def _packed(client, order_id):
    missions = client.post(f"/v1/orders/{order_id}/reserve").json()["missions"]
    with client.app.state.SessionLocal() as db:
        from app.models import Mission
        for m in missions:
            barcode = db.get(Variant, db.get(Mission, m["id"]).variant_id).barcode
            assert client.post(f"/v1/missions/{m['id']}/scan-confirm", json={"barcode": barcode}).status_code == 200
    package = client.post(f"/v1/orders/{order_id}/pack").json()["package_id"]
    assert client.post(f"/v1/packages/{package}/weight", json={"weight_g": 400}).status_code == 200


def test_shipping_a_paypal_order_sends_the_tracking_to_paypal(shop, pp):
    order, o = _paid(shop, pp)
    _packed(shop, o.id)
    r = shop.post(f"/v1/orders/{o.id}/ship", json={"carrier": "Canada Post", "tracking_code": "7023210039414604"})
    assert r.status_code == 200, r.text
    assert r.json()["paypal_tracking"]["pushed"] is True
    track = [b for m, p, b in pp.requests if p.endswith("/track")]
    assert track and track[0]["carrier"] == "CANADA_POST" and track[0]["capture_id"] == o.paypal_capture_id
    assert _order(shop, order["order_number"]).paypal_tracking_id


def test_tracking_that_failed_is_retried_by_the_timer(shop, pp, monkeypatch):
    order, o = _paid(shop, pp)
    _packed(shop, o.id)
    real = pp.__call__

    def down(request):
        if request.url.path.endswith("/track"):
            return httpx.Response(503, json={"name": "SERVICE_UNAVAILABLE"})
        return real(request)
    monkeypatch.setattr(paypal, "TRANSPORT", httpx.MockTransport(down))
    r = shop.post(f"/v1/orders/{o.id}/ship", json={"carrier": "Meest", "tracking_code": "MEEST123"})
    assert r.status_code == 200 and r.json()["paypal_tracking"]["pushed"] is False
    assert _order(shop, order["order_number"]).state == "HANDOFF_COMPLETE"
    monkeypatch.setattr(paypal, "TRANSPORT", httpx.MockTransport(pp))
    sweep = shop.post("/v1/notifications/order-mail").json()
    assert sweep["paypal_tracking_pushed"] == 1
    other = [b for m, p, b in pp.requests if p.endswith("/track")][-1]
    assert other["carrier"] == "OTHER" and other["carrier_name_other"] == "Meest"


def test_cancelled_paid_order_is_refunded_through_paypal_and_the_problem_closes(shop, pp):
    order, o = _paid(shop, pp)
    assert shop.post(f"/v1/admin/orders/{o.id}/paypal/refund", json={}).status_code == 409  # not cancelled yet
    assert shop.post(f"/v1/admin/orders/{o.id}/cancel", json={"note": "Buyer changed their mind"}).status_code == 200
    r = shop.post(f"/v1/admin/orders/{o.id}/paypal/refund", json={"note": "Refund for your cancelled order"})
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["payment"]["paypal"]["refund_id"].startswith("REF") and detail["payment"]["paypal"]["refundable"] is False
    assert all(e["state"] != "OPEN" for e in detail["exceptions"] if e["kind"] == "REFUND_DUE")
    refunds = [b for m, p, b in pp.requests if p.endswith("/refund")]
    assert refunds[0]["amount"] == {"currency_code": "CAD", "value": f"{order['totals']['total_cad']:.2f}"}
    # Twice is once.
    shop.post(f"/v1/admin/orders/{o.id}/paypal/refund", json={})
    assert len([1 for m, p, b in pp.requests if p.endswith("/refund")]) == 1


# ------------------------------------------------------------------ the concierge's guard rails

class ScriptedModel:
    """A chat-completions server that plays back tool calls, then a sentence."""

    def __init__(self, calls):
        self.calls = list(calls)
        self.seen = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.seen.append(body)
        if self.calls:
            name, args = self.calls.pop(0)
            msg = {"role": "assistant", "content": "", "tool_calls": [{"id": f"c{len(self.seen)}", "type": "function",
                                                                       "function": {"name": name, "arguments": json.dumps(args)}}]}
        else:
            msg = {"role": "assistant", "content": "Done."}
        return httpx.Response(200, json={"choices": [{"message": msg}]})


def _chat(shop, monkeypatch, calls, **extra):
    model = ScriptedModel(calls)
    monkeypatch.setattr(llm, "TRANSPORT", httpx.MockTransport(model))
    monkeypatch.setenv("AI_API_KEY", "k")
    r = shop.post("/v1/agent/shop", json={"messages": [{"role": "user", "content": "a gift"}], **extra})
    assert r.status_code == 200, r.text
    return r.json(), model


def _tool_result(model, name):
    for body in model.seen:
        for m in body["messages"]:
            if m.get("role") == "tool" and m.get("name") == name:
                yield json.loads(m["content"])


def test_concierge_cannot_go_over_the_buyers_limit(shop, monkeypatch):
    sku = _sku(shop, "kosiv-nyzynka-blouse")  # CA$ 340
    out, model = _chat(shop, monkeypatch, [("propose_bag", {"lines": [{"sku": sku, "qty": 1}]})], budget_cad=150)
    result = next(_tool_result(model, "propose_bag"))
    assert "Over the spending limit" in result["error"]
    assert not [c for c in out["cards"] if c["type"] == "bag"]


def test_concierge_prices_from_the_shop_and_prepares_a_checkout_without_placing_it(shop, monkeypatch):
    sku = _sku(shop)
    args = {"lines": [{"sku": sku, "quantity": 1}], "email": "olena@example.com", "name": "Olena K",
            "ship_to": {"street": "120 Queen St W", "city": "Toronto", "province": "ON", "postal_code": "M5H2N2"}}
    out, _ = _chat(shop, monkeypatch, [("prepare_checkout", args)])
    card = next(c for c in out["cards"] if c["type"] == "checkout")
    quote = shop.post("/v1/storefront/quote", json={"lines": [{"sku": sku, "qty": 1}], "fulfillment_method": "SHIP",
                                                    "ship_to": {"province": "ON"}}).json()
    assert card["totals"]["total_cad"] == quote["total_cad"]
    assert card["ship_to"]["street1"] == "120 Queen St W" and card["ship_to"]["postal_code"] == "M5H 2N2"
    with shop.app.state.SessionLocal() as db:
        assert db.scalar(select(Order)) is None  # nothing is placed until the buyer presses PayPal


def test_concierge_reports_only_its_own_orders(shop, pp, monkeypatch):
    order, _ = _paid(shop, pp)
    out, model = _chat(shop, monkeypatch, [("order_status", {"order_number": order["order_number"]})])
    assert "error" in next(_tool_result(model, "order_status"))
    out, model = _chat(shop, monkeypatch, [("order_status", {"order_number": order["order_number"]})],
                       orders=[{"order_number": order["order_number"], "token": order["access_token"]}])
    assert next(_tool_result(model, "order_status"))["paid"] is True


def test_desk_proposes_and_does_not_act(shop, pp, monkeypatch):
    order, o = _paid(shop, pp)
    shop.post(f"/v1/admin/orders/{o.id}/cancel", json={"note": "Out of stock at the maker"})
    model = ScriptedModel([("paypal_reconcile", {}), ("propose_action", {"kind": "refund", "order_number": order["order_number"]})])
    monkeypatch.setattr(llm, "TRANSPORT", httpx.MockTransport(model))
    monkeypatch.setenv("AI_API_KEY", "k")
    r = shop.post("/v1/admin/agent/desk", json={"messages": [{"role": "user", "content": "anything to refund?"}]})
    assert r.status_code == 200, r.text
    out = r.json()
    recon = next(_tool_result(model, "paypal_reconcile"))
    assert order["order_number"] in recon["cancelled_paid_not_refunded"]
    assert out["actions"][0]["kind"] == "refund" and out["actions"][0]["order_id"] == o.id
    assert not [1 for m, p, b in pp.requests if p.endswith("/refund")]  # proposing moved no money
