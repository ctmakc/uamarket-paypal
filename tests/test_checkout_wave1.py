"""Wave 1: an order that completes, honestly, and stock that cannot be sold twice.

Covers the routable-address rule in the API, the "not taking orders" state, the local fake
card provider running through the Stripe webhook path, amount/currency checks, session
expiry and retry, placement holds and their sweep, split reservations, the typed quote,
manual shipping with tracking, the mail preview and the frozen "order received" email.
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.models import ExceptionRecord, InventoryBalance, Order, Reservation, Variant, now_utc
from app.services import mailer
from app.services.ratelimit import lookup_limiter, order_limiter
from app.services.routable import is_routable_email
from app.services.storefront import ConfigurationError, sign_stripe_payload

SHOP_ENV = (
    "PAYMENT_PROVIDER", "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "ETRANSFER_EMAIL", "SHOP_CONTACT_EMAIL",
    "SHOP_CATALOGUE_STATUS", "WEB_INDEXABLE", "ORDER_HOLD_MINUTES", "SMTP_HOST", "MAIL_FROM", "TAX_RATES_JSON",
)
BUYER = "buyer@example.test"


class FakeTransport:
    def __init__(self):
        self.messages = []

    def __call__(self, config, message):
        self.messages.append(message)

    def bodies(self) -> list[str]:
        return [m.get_body(preferencelist=("plain",)).get_content() for m in self.messages]


@pytest.fixture()
def env(monkeypatch):
    for key in SHOP_ENV:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("WEB_BASE_URL", "http://localhost:3000")
    monkeypatch.setenv("TAX_RATES_JSON", json.dumps({"ON": 0.13}))
    order_limiter.reset()
    lookup_limiter.reset()
    return monkeypatch


def _client(tmp_path, *, stock: bool = True) -> TestClient:
    client = TestClient(create_app(f"sqlite:///{tmp_path / f'w1-{uuid.uuid4().hex[:6]}.db'}", create_schema=True))
    assert client.post("/admin/seed-catalog", params={"with_stock": str(stock).lower()}).status_code == 200
    return client


@pytest.fixture()
def fake_shop(env, tmp_path):
    """Placeholder catalogue, fake card payments, mail caught by a fake transport."""
    env.setenv("PAYMENT_PROVIDER", "fake")
    env.setenv("SMTP_HOST", "mailpit")
    env.setenv("MAIL_FROM", "UA Market <shop@uamarket.local>")
    return _client(tmp_path)


@pytest.fixture()
def transport(monkeypatch):
    fake = FakeTransport()
    monkeypatch.setattr(mailer, "TRANSPORT", fake)
    return fake


def _sku(client, slug="opishnia-mug") -> str:
    product = client.get(f"/v1/catalog/products/{slug}").json()
    return next(v["sku"] for v in product["variants"] if v["availability"]["in_stock"])


def _payload(lines, **extra):
    body = {
        "idempotency_key": f"w1-{uuid.uuid4()}",
        "email": BUYER,
        "name": "Olena Buyer",
        "fulfillment_method": "SHIP",
        "ship_to": {"street1": "1 Main St", "city": "Kanata", "province": "ON", "postal_code": "K2K 1X1"},
        "lines": lines,
    }
    body.update(extra)
    return body


def _order(client, number) -> Order:
    with client.app.state.SessionLocal() as db:
        return db.scalar(select(Order).where(Order.order_number == number))


def _stock_one(client, sku, *, where=(("A-LANE-01", 1),)):
    for location, qty in where:
        r = client.post("/v1/receipts", json={"sku": sku, "location_id": location, "qty": qty, "reference_id": f"PO-{location}"})
        assert r.status_code == 200, r.text


# ------------------------------------------------------------------ addresses and config

def test_routable_email_rule():
    for good in ("pay@uamarket-fixture.ca", "UA Market <shop@shop.ca>", "a.b@mail.co.uk"):
        assert is_routable_email(good), good
    for bad in ("", None, "pay@uamarket.local", "x@shop.test", "x@y.invalid", "x@example.com", "x@example.ca",
                "x@foo.example", "x@host.internal", "nobody", "a@b", "UA <shop@uamarket.localhost>"):
        assert not is_routable_email(bad), bad


def test_placeholder_etransfer_address_means_no_orders(env, tmp_path):
    env.setenv("ETRANSFER_EMAIL", "pay@uamarket.local")
    env.setenv("SHOP_CONTACT_EMAIL", "hello@uamarket.local")
    client = _client(tmp_path)
    cfg = client.get("/v1/storefront/config").json()
    assert "ETRANSFER" not in cfg["payment_methods"]
    assert cfg["payment_methods"] == [] and cfg["taking_orders"] is False
    assert cfg["etransfer_email"] is None and cfg["contact_email"] is None
    r = client.post("/v1/storefront/orders", json=_payload([{"sku": _sku(client), "qty": 1}]))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "not_taking_orders"


def test_placeholder_sender_disables_mail_except_for_a_local_catcher(env, tmp_path):
    env.setenv("SMTP_HOST", "smtp.realhost.ca")
    env.setenv("MAIL_FROM", "UA Market <shop@uamarket.local>")
    assert mailer.load_config().enabled is False
    env.setenv("SMTP_HOST", "mailpit")
    assert mailer.load_config().enabled is True


def test_stripe_needs_both_the_key_and_the_webhook_secret(env, tmp_path):
    client = _client(tmp_path)
    env.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    assert client.get("/v1/storefront/config").json()["payment_methods"] == []
    env.setenv("STRIPE_WEBHOOK_SECRET", "whsec_x")
    assert client.get("/v1/storefront/config").json()["payment_methods"] == ["STRIPE"]


def test_fake_provider_is_refused_on_an_indexable_or_live_shop(env, tmp_path):
    env.setenv("PAYMENT_PROVIDER", "fake")
    env.setenv("WEB_INDEXABLE", "true")
    with pytest.raises(ConfigurationError):
        create_app(f"sqlite:///{tmp_path / 'a.db'}", create_schema=True)
    env.setenv("WEB_INDEXABLE", "false")
    env.setenv("SHOP_CATALOGUE_STATUS", "live")
    with pytest.raises(ConfigurationError):
        create_app(f"sqlite:///{tmp_path / 'b.db'}", create_schema=True)


def test_health_runs_a_query_and_schema_is_left_to_alembic(env, tmp_path):
    client = _client(tmp_path)
    body = client.get("/health").json()
    assert body["ok"] is True and body["database"] == "ok"
    env.setenv("ALLOW_INSECURE_DEV", "false")
    bare = create_app(f"sqlite:///{tmp_path / 'bare.db'}")
    from sqlalchemy import inspect
    assert inspect(bare.state.engine).get_table_names() == []


# ------------------------------------------------------------------ fake payment end to end

def test_fake_card_payment_runs_the_stripe_path_and_reserves(fake_shop, transport):
    client = fake_shop
    cfg = client.get("/v1/storefront/config").json()
    assert cfg["payment_methods"] == ["STRIPE"] and cfg["payment_test_mode"] is True and cfg["catalogue"] == "placeholder"

    r = client.post("/v1/storefront/orders", json=_payload([{"sku": _sku(client), "qty": 1}]))
    assert r.status_code == 201, r.text
    order = r.json()
    assert order["demo"] is True
    url = order["payment"]["checkout_url"]
    assert url.startswith("http://localhost:3000/pay/test/cs_test_fake_")
    session = url.rsplit("/", 1)[1]

    info = client.get(f"/v1/payments/test/{session}").json()
    assert info["order_number"] == order["order_number"] and info["paid"] is False

    done = client.post(f"/v1/payments/test/{session}/complete")
    assert done.status_code == 200, done.text
    assert done.json()["paid"] is True and done.json()["state"] == "PICK_PLANNED"
    assert client.post(f"/v1/payments/test/{session}/complete").status_code == 200  # replay is harmless

    bodies = transport.bodies()
    assert len(bodies) == 2  # placed, paid
    assert "Do not send money" in bodies[0]
    assert "Nothing is owed" in bodies[1]

    with client.app.state.SessionLocal() as db:
        rows = list(db.scalars(select(Reservation)))
        assert rows and all(r.state == "ACTIVE" for r in rows)


def test_fake_sessions_do_not_exist_without_the_fake_provider(env, tmp_path):
    client = _client(tmp_path)
    assert client.get("/v1/payments/test/cs_test_fake_abc").status_code == 404
    assert client.post("/v1/payments/test/cs_test_fake_abc/complete").status_code == 404


def test_demo_order_withholds_payment_details(env, tmp_path):
    env.setenv("ETRANSFER_EMAIL", "pay@uamarket-fixture.ca")
    client = _client(tmp_path)
    order = client.post("/v1/storefront/orders", json=_payload([{"sku": _sku(client), "qty": 1}])).json()
    assert order["demo"] is True
    assert order["payment"]["demo"] is True
    assert "recipient_email" not in order["payment"]


# ------------------------------------------------------------------ stripe webhook checks

def _stripe_env(env):
    env.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    env.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    env.setenv("SHOP_CATALOGUE_STATUS", "live")


def _stripe_event(order_id, *, amount, currency="cad", kind="checkout.session.completed", session="cs_1"):
    return json.dumps({"id": f"evt_{uuid.uuid4().hex}", "type": kind, "data": {"object": {
        "id": session, "client_reference_id": order_id, "payment_status": "paid" if kind.endswith("completed") else "unpaid",
        "payment_intent": "pi_1", "amount_total": amount, "currency": currency}}}).encode()


def _post_webhook(client, raw):
    return client.post("/webhooks/stripe", content=raw, headers={"stripe-signature": sign_stripe_payload(raw, "whsec_test")})


def _place_card_order(client, env, sku=None, qty=1):
    # Open the order with e-Transfer so no Stripe HTTP call is made, then switch it to card.
    env.setenv("ETRANSFER_EMAIL", "pay@uamarket-fixture.ca")
    r = client.post("/v1/storefront/orders", json=_payload([{"sku": sku or _sku(client), "qty": qty}], payment_method="ETRANSFER"))
    assert r.status_code == 201, r.text
    with client.app.state.SessionLocal() as db:
        row = db.scalar(select(Order).where(Order.order_number == r.json()["order_number"]))
        row.payment_method = "STRIPE"
        row.checkout_session_id = "cs_1"
        db.commit()
        return row.id, r.json()


def test_webhook_with_wrong_amount_or_currency_is_rejected(env, tmp_path):
    _stripe_env(env)
    client = _client(tmp_path)
    order_id, order = _place_card_order(client, env)
    cents = round(order["totals"]["total_cad"] * 100)

    r = _post_webhook(client, _stripe_event(order_id, amount=cents - 1))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "amount_mismatch"
    r = _post_webhook(client, _stripe_event(order_id, amount=cents, currency="usd"))
    assert r.status_code == 400
    with client.app.state.SessionLocal() as db:
        assert db.get(Order, order_id).paid_at is None
        kinds = [e.kind for e in db.scalars(select(ExceptionRecord))]
        assert "PAYMENT_AMOUNT_MISMATCH" in kinds

    r = _post_webhook(client, _stripe_event(order_id, amount=cents))
    assert r.status_code == 200 and r.json()["state"] == "PICK_PLANNED"


def test_expired_session_releases_the_hold_and_retry_needs_stock(env, tmp_path, monkeypatch):
    _stripe_env(env)
    client = _client(tmp_path, stock=False)
    sku = _sku_any(client)
    _stock_one(client, sku)
    order_id, order = _place_card_order(client, env, sku=sku)
    assert _available(client, sku) == 0

    r = _post_webhook(client, _stripe_event(order_id, amount=1, kind="checkout.session.expired"))
    assert r.status_code == 200
    assert _available(client, sku) == 1
    with client.app.state.SessionLocal() as db:
        assert db.get(Order, order_id).payment_ref is None

    # Someone else buys the last unit; the first buyer's retry must not open a card session.
    env.setenv("ETRANSFER_EMAIL", "pay@uamarket-fixture.ca")
    other = client.post("/v1/storefront/orders", json=_payload([{"sku": sku, "qty": 1}], payment_method="ETRANSFER", email="other@example.test"))
    assert other.status_code == 201
    r = client.post(f"/v1/storefront/orders/{order['order_number']}/pay", params={"email": BUYER})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "out_of_stock"


def test_retry_payment_opens_a_new_test_session(fake_shop):
    client = fake_shop
    order = client.post("/v1/storefront/orders", json=_payload([{"sku": _sku(client), "qty": 1}])).json()
    first = order["payment"]["checkout_url"]
    r = client.post(f"/v1/storefront/orders/{order['order_number']}/pay", params={"email": BUYER})
    assert r.status_code == 200, r.text
    second = r.json()["payment"]["checkout_url"]
    assert second != first and second.startswith("http://localhost:3000/pay/test/")
    assert client.get(f"/v1/payments/test/{first.rsplit('/', 1)[1]}").status_code == 404


# ------------------------------------------------------------------ stock

def _sku_any(client, slug="opishnia-mug") -> str:
    return client.get(f"/v1/catalog/products/{slug}").json()["variants"][0]["sku"]


def _available(client, sku) -> int:
    with client.app.state.SessionLocal() as db:
        variant = db.scalar(select(Variant).where(Variant.sku == sku))
        return sum(b.qty_on_hand - b.qty_reserved for b in db.scalars(select(InventoryBalance).where(InventoryBalance.variant_id == variant.id)))


def test_second_order_for_the_last_unit_cannot_reach_payment(fake_shop_no_stock):
    client = fake_shop_no_stock
    sku = _sku_any(client)
    _stock_one(client, sku)

    first = client.post("/v1/storefront/orders", json=_payload([{"sku": sku, "qty": 1}]))
    assert first.status_code == 201 and first.json()["payment"]["checkout_url"]

    quote = client.post("/v1/storefront/quote", json={"lines": [{"sku": sku, "qty": 1}]}).json()
    assert quote["lines"][0]["status"] == "sold_out" and quote["lines"][0]["max_qty"] == 0

    second = client.post("/v1/storefront/orders", json=_payload([{"sku": sku, "qty": 1}], email="second@example.test"))
    assert second.status_code == 409
    detail = second.json()["detail"]
    assert detail["code"] == "out_of_stock" and detail["details"]["lines"][0] == {"sku": sku, "status": "sold_out", "max_qty": 0}


@pytest.fixture()
def fake_shop_no_stock(env, tmp_path):
    env.setenv("PAYMENT_PROVIDER", "fake")
    return _client(tmp_path, stock=False)


def test_expired_hold_is_released_by_the_sweep_and_a_late_payment_raises_a_refund_exception(fake_shop_no_stock):
    client = fake_shop_no_stock
    sku = _sku_any(client)
    _stock_one(client, sku)
    first = client.post("/v1/storefront/orders", json=_payload([{"sku": sku, "qty": 1}])).json()
    session = first["payment"]["checkout_url"].rsplit("/", 1)[1]

    with client.app.state.SessionLocal() as db:
        row = db.scalar(select(Order).where(Order.order_number == first["order_number"]))
        row.hold_expires_at = now_utc() - timedelta(minutes=1)
        db.commit()
    assert client.post("/v1/notifications/order-mail").json()["holds_released"] == 1
    assert _available(client, sku) == 1

    second = client.post("/v1/storefront/orders", json=_payload([{"sku": sku, "qty": 1}], email="second@example.test"))
    assert second.status_code == 201

    # The first buyer pays on the page they still have open.
    paid = client.post(f"/v1/payments/test/{session}/complete").json()
    assert paid["state"] == "OUT_OF_STOCK"
    with client.app.state.SessionLocal() as db:
        rows = [e for e in db.scalars(select(ExceptionRecord).where(ExceptionRecord.kind == "PAID_OUT_OF_STOCK"))]
        assert len(rows) == 1 and "refund" in rows[0].details.lower()


def test_reservation_splits_a_line_across_sellable_locations(fake_shop_no_stock):
    client = fake_shop_no_stock
    sku = _sku_any(client)
    _stock_one(client, sku, where=(("A-LANE-01", 1), ("B-BIN-001", 1), ("EXCEPTION-01", 5)))
    r = client.post("/v1/storefront/orders", json=_payload([{"sku": sku, "qty": 2}]))
    assert r.status_code == 201, r.text
    too_many = client.post("/v1/storefront/quote", json={"lines": [{"sku": sku, "qty": 1}]}).json()
    assert too_many["lines"][0]["status"] == "sold_out"  # the exception shelf never sells
    session = r.json()["payment"]["checkout_url"].rsplit("/", 1)[1]
    assert client.post(f"/v1/payments/test/{session}/complete").json()["state"] == "PICK_PLANNED"
    order = _order(client, r.json()["order_number"])
    missions = client.post(f"/v1/orders/{order.id}/reserve").json()["missions"]
    assert sorted(m["location"] for m in missions) == ["A-LANE-01", "B-BIN-001"]


# ------------------------------------------------------------------ quote

def test_quote_is_typed_and_reports_each_line(fake_shop_no_stock):
    client = fake_shop_no_stock
    assert client.post("/v1/storefront/quote", json={"lines": ["x"]}).status_code == 422
    assert client.post("/v1/storefront/quote", json={"lines": [{"sku": "A", "qty": 21}]}).status_code == 422
    assert client.post("/v1/storefront/quote", json={"lines": "nope"}).status_code == 422

    sku = _sku_any(client)
    _stock_one(client, sku, where=(("A-LANE-01", 3),))
    q = client.post("/v1/storefront/quote", json={"lines": [{"sku": sku, "qty": 20}, {"sku": "NOPE", "qty": 1}]}).json()
    by = {line["sku"]: line for line in q["lines"]}
    assert by[sku]["status"] == "reduce" and by[sku]["max_qty"] == 3
    assert by["NOPE"]["status"] == "sold_out"
    assert q["subtotal_cad"] == round(3 * by[sku]["unit_price_cad"], 2)
    ok = client.post("/v1/storefront/quote", json={"lines": [{"sku": sku, "qty": 2}]}).json()["lines"][0]
    assert {k: ok[k] for k in ("sku", "qty", "status", "max_qty")} == {"sku": sku, "qty": 2, "status": "ok", "max_qty": 2}
    # What the bag prints about the line, and never a stock count.
    assert set(ok) - {"sku", "qty", "unit_price_cad", "status", "max_qty"} <= {
        "slug", "title", "title_uk", "label", "label_uk", "maker", "maker_uk", "origin", "image_url"}


# ------------------------------------------------------------------ ship, preview, frozen placement

def _fulfil_to_packed(client, order_id):
    missions = client.post(f"/v1/orders/{order_id}/reserve").json()["missions"]
    with client.app.state.SessionLocal() as db:
        from app.models import Mission
        for m in missions:
            mission = db.get(Mission, m["id"])
            barcode = db.get(Variant, mission.variant_id).barcode
            assert client.post(f"/v1/missions/{m['id']}/scan-confirm", json={"barcode": barcode}).status_code == 200
    package = client.post(f"/v1/orders/{order_id}/pack").json()["package_id"]
    assert client.post(f"/v1/packages/{package}/weight", json={"weight_g": 400}).status_code == 200
    return package


def test_ship_with_manual_tracking_and_the_customer_sees_it(fake_shop, transport):
    client = fake_shop
    order = client.post("/v1/storefront/orders", json=_payload([{"sku": _sku(client), "qty": 1}], locale="uk")).json()
    session = order["payment"]["checkout_url"].rsplit("/", 1)[1]
    client.post(f"/v1/payments/test/{session}/complete")
    oid = _order(client, order["order_number"]).id

    assert client.post(f"/v1/orders/{oid}/ship", json={"carrier": "Canada Post", "tracking_code": "7023210039414604"}).status_code == 409
    _fulfil_to_packed(client, oid)
    r = client.post(f"/v1/orders/{oid}/ship", json={"carrier": "Canada Post", "tracking_code": "7023210039414604"})
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "HANDOFF_COMPLETE"
    assert r.json()["tracking"] == {"carrier": "Canada Post", "code": "7023210039414604"}
    assert client.post(f"/v1/orders/{oid}/ship", json={"carrier": "Canada Post", "tracking_code": "7023210039414604"}).status_code == 200

    view = client.get(f"/v1/storefront/orders/{order['order_number']}", params={"email": BUYER}).json()
    assert view["status"]["key"] == "shipped" and view["status"]["label"] == "Shipped"
    assert view["tracking"]["code"] == "7023210039414604"
    bodies = transport.bodies()
    assert len(bodies) == 3 and "7023210039414604" in bodies[2]

    with client.app.state.SessionLocal() as db:
        assert all(r.state == "CONSUMED" for r in db.scalars(select(Reservation)))


def test_mail_preview_and_the_placed_email_stays_as_placed(fake_shop, transport):
    client = fake_shop
    order = client.post("/v1/storefront/orders", json=_payload([{"sku": _sku(client), "qty": 1}])).json()
    session = order["payment"]["checkout_url"].rsplit("/", 1)[1]
    client.post(f"/v1/payments/test/{session}/complete")
    oid = _order(client, order["order_number"]).id

    placed = client.get(f"/v1/orders/{oid}/mail/placed/preview", params={"format": "text"})
    assert placed.status_code == 200 and placed.headers["content-type"].startswith("text/plain")
    assert "Nothing is owed" not in placed.text and "Do not send money" in placed.text
    html = client.get(f"/v1/orders/{oid}/mail/paid/preview")
    assert html.status_code == 200 and html.headers["content-type"].startswith("text/html")
    assert "Nothing is owed" in html.text
    assert client.get(f"/v1/orders/{oid}/mail/nonsense/preview").status_code == 404
    assert len(transport.messages) == 2  # previews send nothing


def test_preview_and_ship_are_operator_only(env, tmp_path):
    client = _client(tmp_path)
    env.setenv("ALLOW_INSECURE_DEV", "false")
    env.setenv("OPERATOR_API_KEY", "op")
    env.setenv("ADMIN_API_KEY", "ad")
    assert client.get("/v1/orders/x/mail/placed/preview").status_code == 401
    assert client.post("/v1/orders/x/ship", json={"carrier": "CP", "tracking_code": "123"}).status_code == 401


def test_scheduler_pass_releases_expired_holds(fake_shop_no_stock):
    from app.scheduler import run_once
    client = fake_shop_no_stock
    sku = _sku_any(client)
    _stock_one(client, sku)
    order = client.post("/v1/storefront/orders", json=_payload([{"sku": sku, "qty": 1}])).json()
    with client.app.state.SessionLocal() as db:
        row = db.scalar(select(Order).where(Order.order_number == order["order_number"]))
        row.hold_expires_at = now_utc() - timedelta(seconds=1)
        db.commit()
    result = run_once(client.app.state.SessionLocal)
    assert result["holds_released"] == 1
    assert _available(client, sku) == 1
