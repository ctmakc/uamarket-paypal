"""Wave 3: tax lines, provinces the shop does not ship to, the order key, the client address,
search in two languages, the bag's quote data and the order email.
"""
from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import mailer, search, tax
from app.services.ratelimit import lookup_limiter, order_invalid_limiter, order_limiter

BUYER = "buyer@example.test"
ENV = (
    "PAYMENT_PROVIDER", "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "ETRANSFER_EMAIL", "SHOP_CONTACT_EMAIL",
    "SHOP_CATALOGUE_STATUS", "WEB_INDEXABLE", "SMTP_HOST", "MAIL_FROM", "TAX_RATES_JSON", "SHOP_TAX_MODE",
    "SHOP_PST_REGISTERED_PROVINCES", "SHOP_GST_NUMBER", "SHOP_SHIP_EXCLUDE_PROVINCES", "INTERNAL_PROXY_SECRET",
    "TRUSTED_PROXY_IPS", "SHOP_TERMS_VERSION", "SHOP_LEGAL_NAME", "SHOP_BUSINESS_ADDRESS", "SHOP_PRIVACY_EMAIL",
    "EASYPOST_API_KEY", "SHOP_HOSTING_PROVIDER", "MAIL_PROVIDER_NAME",
)


class FakeTransport:
    def __init__(self):
        self.messages = []

    def __call__(self, config, message):
        self.messages.append(message)


@pytest.fixture()
def env(monkeypatch):
    for key in ENV:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("WEB_BASE_URL", "http://localhost:3000")
    monkeypatch.setenv("PAYMENT_PROVIDER", "fake")
    monkeypatch.setenv("SMTP_HOST", "mailpit")
    monkeypatch.setenv("MAIL_FROM", "UA Market <shop@uamarket.local>")
    for limiter in (order_limiter, order_invalid_limiter, lookup_limiter):
        limiter.reset()
    return monkeypatch


@pytest.fixture()
def shop(env, tmp_path):
    client = TestClient(create_app(f"sqlite:///{tmp_path / f'w3-{uuid.uuid4().hex[:6]}.db'}", create_schema=True))
    assert client.post("/admin/seed-catalog").status_code == 200
    return client


@pytest.fixture()
def transport(monkeypatch):
    fake = FakeTransport()
    monkeypatch.setattr(mailer, "TRANSPORT", fake)
    return fake


def _sku(client, slug="opishnia-mug") -> str:
    product = client.get(f"/v1/catalog/products/{slug}").json()
    return next(v["sku"] for v in product["variants"] if v["availability"]["in_stock"])


def _payload(lines, province="ON", **extra):
    body = {
        "idempotency_key": f"w3-{uuid.uuid4()}",
        "email": BUYER,
        "name": "Olena Buyer",
        "fulfillment_method": "SHIP",
        "ship_to": {"street1": "1 Main St", "city": "Town", "province": province, "postal_code": "K2K 1X1"},
        "lines": lines,
    }
    body.update(extra)
    return body


# ------------------------------------------------------------------ tax

def test_tax_modes_and_named_lines(env):
    assert tax.tax_mode() == "unregistered"
    assert tax.tax_lines(100, "ON") == []
    env.setenv("TAX_RATES_JSON", json.dumps({"ON": 0.13}))
    assert tax.tax_mode() == "custom"
    assert [(l["code"], l["amount_cad"]) for l in tax.tax_lines(100, "ON")] == [("TAX", 13.0)]
    env.setenv("SHOP_TAX_MODE", "gst_hst_registered")
    assert [(l["code"], l["rate"], l["amount_cad"], l["label"]) for l in tax.tax_lines(100, "AB")] == [("GST", 0.05, 5.0, "GST (5%)")]
    assert [(l["code"], l["amount_cad"]) for l in tax.tax_lines(100, "ON")] == [("HST", 13.0)]
    assert [(l["code"], l["amount_cad"]) for l in tax.tax_lines(100, "NS")] == [("HST", 14.0)]
    assert [(l["code"], l["amount_cad"]) for l in tax.tax_lines(100, "BC")] == [("GST", 5.0)]
    env.setenv("SHOP_PST_REGISTERED_PROVINCES", "BC, QC")
    assert [(l["code"], l["amount_cad"]) for l in tax.tax_lines(100, "BC")] == [("GST", 5.0), ("PST", 7.0)]
    assert [(l["code"], l["amount_cad"]) for l in tax.tax_lines(100, "QC")] == [("GST", 5.0), ("QST", 9.98)]
    assert tax.tax_lines(100, "MB")[-1]["code"] == "GST"


def test_alberta_ontario_and_quebec_at_checkout(shop, env):
    env.setenv("SHOP_TAX_MODE", "gst_hst_registered")
    env.setenv("SHOP_GST_NUMBER", "123456789 RT0001")
    sku = _sku(shop)
    ab = shop.post("/v1/storefront/quote", json={"lines": [{"sku": sku, "qty": 1}], "ship_to": {"province": "AB"}}).json()
    assert [(l["code"], l["label"]) for l in ab["tax_lines"]] == [("GST", "GST (5%)")]
    assert ab["tax_cad"] == round((ab["subtotal_cad"] + ab["shipping_cad"]) * 0.05, 2)
    on = shop.post("/v1/storefront/quote", json={"lines": [{"sku": sku, "qty": 1}], "ship_to": {"province": "ON"}}).json()
    assert [(l["code"], l["label"]) for l in on["tax_lines"]] == [("HST", "HST (13%)")]
    assert on["ship_blocked"] is None

    qc = shop.post("/v1/storefront/quote", json={"lines": [{"sku": sku, "qty": 1}], "ship_to": {"province": "QC"}}).json()
    assert qc["ship_blocked"]["province"] == "QC" and "French" in qc["ship_blocked"]["message"]
    refused = shop.post("/v1/storefront/orders", json=_payload([{"sku": sku, "qty": 1}], province="QC"))
    assert refused.status_code == 400
    assert refused.json()["detail"]["code"] == "province_excluded"
    assert "Квебек" in refused.json()["detail"]["details"]["message_uk"]

    placed = shop.post("/v1/storefront/orders", json=_payload([{"sku": sku, "qty": 1}], province="AB"))
    assert placed.status_code == 201, placed.text
    view = placed.json()
    assert [l["code"] for l in view["totals"]["tax_lines"]] == ["GST"]
    assert view["gst_number"] == "123456789 RT0001"

    cfg = shop.get("/v1/storefront/config").json()
    assert cfg["shipping"]["excluded_provinces"] == ["QC"]
    assert cfg["tax"]["mode"] == "gst_hst_registered" and "QC" in cfg["tax"]["configured_provinces"]


def test_excluded_provinces_setting(env):
    from app.services.storefront import excluded_provinces
    assert excluded_provinces() == ["QC"]
    env.setenv("SHOP_SHIP_EXCLUDE_PROVINCES", "none")
    assert excluded_provinces() == []
    env.setenv("SHOP_SHIP_EXCLUDE_PROVINCES", "qc, nu, XX")
    assert excluded_provinces() == ["NU", "QC"]


# ------------------------------------------------------------------ the order key

def test_order_page_key_replaces_the_email(shop, transport):
    sku = _sku(shop)
    placed = shop.post("/v1/storefront/orders", json=_payload([{"sku": sku, "qty": 1}], terms_accepted=True)).json()
    number, token = placed["order_number"], placed["access_token"]
    assert token and "@" not in token

    assert shop.get(f"/v1/storefront/orders/{number}", headers={"x-order-token": token}).status_code == 200
    assert shop.get(f"/v1/storefront/orders/{number}", headers={"x-order-token": "wrong" + token[5:]}).status_code == 404
    assert "access_token" not in shop.get(f"/v1/storefront/orders/{number}", headers={"x-order-token": token}).json()

    looked = shop.post("/v1/storefront/orders/lookup", json={"order_number": number.lower(), "email": BUYER.upper()})
    assert looked.status_code == 200 and looked.json()["access_token"] == token
    assert shop.post("/v1/storefront/orders/lookup", json={"order_number": number, "email": "x@example.test"}).status_code == 404

    # The payment return link and the email link carry the key and never the address.
    assert "@" not in placed["payment"]["checkout_url"]
    body = transport.messages[0].get_body(preferencelist=("plain",)).get_content()
    link = next(line for line in body.splitlines() if "/order/" in line)
    assert f"key={token}" in link and "email=" not in link and "%40" not in link

    cancelled = shop.post(f"/v1/storefront/orders/{number}/cancel", headers={"x-order-token": token})
    assert cancelled.status_code == 200 and cancelled.json()["status"]["key"] == "cancelled"
    with shop.app.state.SessionLocal() as db:
        from sqlalchemy import select
        from app.models import Order
        order = db.scalar(select(Order).where(Order.order_number == number))
        assert json.loads(order.placement_json)["terms"]["accepted"] is True


# ------------------------------------------------------------------ client address

def _plenty(client, sku):
    r = client.post("/v1/receipts", json={"sku": sku, "location_id": "A-LANE-01", "qty": 200, "reference_id": "PO-W3"})
    assert r.status_code == 200, r.text


def test_client_address_needs_the_internal_secret(shop, env, transport):
    sku = _sku(shop)
    _plenty(shop, sku)
    env.setenv("INTERNAL_PROXY_SECRET", "s" * 32)
    # Forged headers without the secret: all twelve land on one address and the 11th is refused.
    codes = [shop.post("/v1/storefront/orders", json=_payload([{"sku": sku, "qty": 1}]),
                       headers={"x-forwarded-for": f"7.7.7.{i}", "x-client-ip": f"8.8.8.{i}"}).status_code
             for i in range(12)]
    assert codes[:10] == [201] * 10 and codes[10:] == [429, 429], codes

    order_limiter.reset()
    # With the secret, two real addresses have two buckets.
    for ip in ("203.0.113.1", "203.0.113.2"):
        for _ in range(10):
            r = shop.post("/v1/storefront/orders", json=_payload([{"sku": sku, "qty": 1}]),
                          headers={"x-internal-proxy-secret": "s" * 32, "x-client-ip": ip})
            assert r.status_code == 201, r.text
    blocked = shop.post("/v1/storefront/orders", json=_payload([{"sku": sku, "qty": 1}]),
                        headers={"x-internal-proxy-secret": "s" * 32, "x-client-ip": "203.0.113.1"})
    assert blocked.status_code == 429
    wrong = shop.post("/v1/storefront/orders", json=_payload([{"sku": sku, "qty": 1}]),
                      headers={"x-internal-proxy-secret": "t" * 32, "x-client-ip": "203.0.113.9"})
    assert wrong.status_code == 201  # counted under the socket peer, which has a fresh bucket


def test_validation_failures_use_their_own_bucket(shop, transport):
    sku = _sku(shop)
    for _ in range(15):
        bad = shop.post("/v1/storefront/orders", json=_payload([{"sku": sku, "qty": 1}], email="not-an-email"))
        assert bad.status_code == 400
    assert shop.post("/v1/storefront/orders", json=_payload([{"sku": sku, "qty": 1}])).status_code == 201
    codes = [shop.post("/v1/storefront/orders", json=_payload([{"sku": sku, "qty": 1}], email="nope")).status_code for _ in range(20)]
    assert codes[-1] == 429


# ------------------------------------------------------------------ search

@pytest.mark.parametrize("query,slug", [
    ("вишиванка", "kosiv-nyzynka-blouse"), ("vyshyvanka", "kosiv-nyzynka-blouse"), ("vyshyvanky", "borshchiv-black-blouse"),
    ("blouse", "everyday-blouse-women"), ("сорочки", "kosiv-mens-shirt"), ("рушник", "rushnyk-whitework"),
    ("rushnyk", "rushnyk-wedding-kosiv"), ("towel", "rushnyk-whitework"), ("motanka", "motanka-classic"),
    ("мотанки", "motanka-mini"), ("doll", "motanka-classic"), ("кераміка", "opishnia-mug"), ("Opishnia", "opishnia-lion"),
    ("Опішня", "opishnia-bowl-set"), ("CERAMICS", "opishnia-mug"), ("вишиванк", "kids-shirt-classic"),
])
def test_search_in_two_languages(shop, query, slug):
    found = shop.get("/v1/catalog/products", params={"q": query, "limit": 60}).json()
    assert slug in [i["slug"] for i in found["items"]], (query, [i["slug"] for i in found["items"]])


def test_search_stays_narrow_and_suggests_a_shelf(shop):
    rushnyky = {i["slug"] for i in shop.get("/v1/catalog/products", params={"q": "рушник"}).json()["items"]}
    assert rushnyky == {"rushnyk-wedding-kosiv", "rushnyk-whitework"}
    empty = shop.get("/v1/catalog/products", params={"q": "qwzxv"}).json()
    assert empty["total"] == 0 and empty["suggestion"]["category"]
    near = shop.get("/v1/catalog/products", params={"q": "ceramicks mugz lion"}).json()
    assert near["total"] == 0 or near["items"]
    assert search.fold("Опі́шня") == "опішня"


# ------------------------------------------------------------------ the bag's quote and the email

def test_quote_lines_carry_both_languages(shop):
    product = shop.get("/v1/catalog/products/kosiv-nyzynka-blouse").json()
    variant = next(v for v in product["variants"] if v["label_uk"])
    q = shop.post("/v1/storefront/quote", json={"lines": [{"sku": variant["sku"], "qty": 1}]}).json()
    line = q["lines"][0]
    assert line["title_uk"] == product["title_uk"] and line["label_uk"] == variant["label_uk"]
    assert line["slug"] == "kosiv-nyzynka-blouse" and line["maker_uk"]


def test_ukrainian_email_uses_ukrainian_labels_and_the_kanva_layout(shop, env, transport):
    env.setenv("SHOP_TAX_MODE", "gst_hst_registered")
    env.setenv("SHOP_GST_NUMBER", "123456789 RT0001")
    env.setenv("SHOP_TERMS_VERSION", "2026-09-17")
    product = shop.get("/v1/catalog/products/kosiv-nyzynka-blouse").json()
    variant = next(v for v in product["variants"] if v["availability"]["in_stock"] and v["label_uk"])
    placed = shop.post("/v1/storefront/orders", json=_payload([{"sku": variant["sku"], "qty": 1}], locale="uk"))
    assert placed.status_code == 201, placed.text
    message = transport.messages[-1]
    text = message.get_body(preferencelist=("plain",)).get_content()
    html = message.get_body(preferencelist=("html",)).get_content()
    assert variant["label_uk"] in text and variant["label"] not in text
    assert "HST (13%)" in text and "123456789 RT0001" in text
    assert "http://localhost:3000/uk/terms" in text and "2026-09-17" in text
    assert "#D9D2C1" in html and "Fira Mono" in html and variant["label_uk"] in html
    assert "Відкрити замовлення" in html


def test_business_block_and_processors_follow_configuration(shop, env):
    cfg = shop.get("/v1/storefront/config").json()
    assert cfg["business"]["legal_name"] is None and cfg["business"]["address"] is None
    assert [p["kind"] for p in cfg["processors"]] == ["hosting"]  # Mailpit is local, not a processor
    env.setenv("SHOP_LEGAL_NAME", "Example Trading Inc.")
    env.setenv("SMTP_HOST", "smtp.mailer-fixture.ca")
    env.setenv("MAIL_FROM", "UA Market <shop@shop-fixture.ca>")
    env.setenv("EASYPOST_API_KEY", "ep-test")
    cfg = shop.get("/v1/storefront/config").json()
    assert cfg["business"]["legal_name"] == "Example Trading Inc."
    assert [p["kind"] for p in cfg["processors"]] == ["email", "shipping", "hosting"]
    assert cfg["processors"][0]["name"] == "smtp.mailer-fixture.ca"
