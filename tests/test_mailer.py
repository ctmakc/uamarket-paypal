"""Order email: disabled until SMTP is configured, and truthful when it is.

Nothing here touches a network. The SMTP transport is replaced by a fake that keeps the
message it was handed, so the assertions are about what the customer would actually read.
"""
from __future__ import annotations

import json
import logging
import smtplib
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.models import ExceptionRecord, Order, OutboxMessage
from app.services import mailer
from app.services.ratelimit import lookup_limiter, order_limiter
from app.services.storefront import MAIL_MAX_ATTEMPTS, mail_key

SMTP_ENV = {
    "SMTP_HOST": "smtp.example.test",
    "SMTP_PORT": "587",
    "SMTP_USER": "shop@uamarket-fixture.ca",
    "SMTP_PASSWORD": "s3cret-not-in-the-log",
    "MAIL_FROM": "UA Market <shop@uamarket-fixture.ca>",
    "MAIL_REPLY_TO": "hello@uamarket-fixture.ca",
    "SHOP_NAME": "UA Market",
}


class FakeTransport:
    """Stands in for the SMTP conversation and keeps every message it was given."""

    def __init__(self, error: Exception | None = None):
        self.error = error
        self.messages = []
        self.configs = []

    def __call__(self, config, message):
        self.configs.append(config)
        if self.error:
            raise self.error
        self.messages.append(message)

    @property
    def last(self):
        return self.messages[-1]

    def body(self, index: int = -1) -> str:
        return self.messages[index].get_body(preferencelist=("plain",)).get_content()

    def html(self, index: int = -1) -> str:
        return self.messages[index].get_body(preferencelist=("html",)).get_content()


def _clear_mail_env(monkeypatch):
    for key in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_SECURITY",
                "SMTP_TIMEOUT_SECONDS", "MAIL_FROM", "MAIL_REPLY_TO", "SHOP_NAME"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture()
def transport(monkeypatch):
    fake = FakeTransport()
    monkeypatch.setattr(mailer, "TRANSPORT", fake)
    return fake


@pytest.fixture()
def shop(tmp_path, monkeypatch):
    """A storefront with e-Transfer payment and SMTP configured."""
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.setenv("ETRANSFER_EMAIL", "pay@uamarket-fixture.ca")
    # These tests exercise a shop selling its real catalogue; demo orders withhold payment details.
    monkeypatch.setenv("SHOP_CATALOGUE_STATUS", "live")
    monkeypatch.setenv("SHOP_CONTACT_EMAIL", "hello@uamarket-fixture.ca")
    monkeypatch.setenv("TAX_RATES_JSON", json.dumps({"ON": 0.13}))
    monkeypatch.setenv("SHIPPING_FLAT_CAD", "12")
    monkeypatch.setenv("SHIPPING_FREE_OVER_CAD", "150")
    monkeypatch.setenv("WEB_BASE_URL", "https://uamarket.example")
    for key, value in SMTP_ENV.items():
        monkeypatch.setenv(key, value)
    order_limiter.reset()
    lookup_limiter.reset()
    client = TestClient(create_app(f"sqlite:///{tmp_path / 'mailer.db'}", create_schema=True))
    assert client.post("/admin/seed-catalog").status_code == 200
    return client


def _variant(client, slug: str = "opishnia-mug") -> dict:
    product = client.get(f"/v1/catalog/products/{slug}").json()
    healthy = [v for v in product["variants"] if v["availability"]["in_stock"] and not v["availability"]["low"]]
    return healthy[0] if healthy else next(v for v in product["variants"] if v["availability"]["in_stock"])


def _place(client, *, locale: str = "en", qty: int = 1, slug: str = "opishnia-mug") -> dict:
    variant = _variant(client, slug)
    payload = {
        "idempotency_key": f"mail-{uuid.uuid4()}",
        "email": "buyer@example.test",
        "name": "Olena Buyer",
        "locale": locale,
        "fulfillment_method": "SHIP",
        "ship_to": {"street1": "1 Main St", "city": "Ottawa", "province": "ON", "postal_code": "K1A 0B1"},
        "lines": [{"sku": variant["sku"], "qty": qty}],
    }
    response = client.post("/v1/storefront/orders", json=payload)
    assert response.status_code == 201, response.text
    return response.json() | {"idempotency_key": payload["idempotency_key"], "variant": variant}


def _order_id(client, number: str) -> str:
    with client.app.state.SessionLocal() as db:
        return db.scalar(select(Order.id).where(Order.order_number == number))


def _rows(client, order_id: str) -> dict[str, OutboxMessage]:
    with client.app.state.SessionLocal() as db:
        rows = db.scalars(select(OutboxMessage).where(OutboxMessage.topic == "notify/email",
                                                      OutboxMessage.aggregate_id == order_id))
        return {row.idempotency_key: (row.state, row.attempt_count) for row in rows}


# --------------------------------------------------------------------------- disabled

def test_unconfigured_mailer_is_disabled_sends_nothing_and_logs_the_message(monkeypatch, caplog):
    _clear_mail_env(monkeypatch)
    # The body of an unsent message is written only when the operator asks for it:
    # MAIL_LOG_BODIES is off by default so a one-time locker code cannot land in the log.
    monkeypatch.setenv("MAIL_LOG_BODIES", "true")

    def explode(config, message):  # pragma: no cover - proves the transport is not reached
        raise AssertionError("a disabled mailer must not open a connection")

    monkeypatch.setattr(mailer, "TRANSPORT", explode)
    assert mailer.email_enabled() is False
    assert mailer.sender_address() is None

    with caplog.at_level(logging.INFO, logger="uamarket.mail"):
        result = mailer.send_email(to="buyer@example.test", subject="Order UA-1", text="Total CA$ 10.00")

    assert result.sent is False and result.disabled is True and result.error is None
    assert "buyer@example.test" in caplog.text
    assert "Order UA-1" in caplog.text
    assert "Total CA$ 10.00" in caplog.text  # the operator can read what was not sent


def test_disabled_shop_says_so_in_its_config_and_records_the_skip(tmp_path, monkeypatch):
    _clear_mail_env(monkeypatch)
    monkeypatch.setenv("ETRANSFER_EMAIL", "pay@uamarket-fixture.ca")
    # These tests exercise a shop selling its real catalogue; demo orders withhold payment details.
    monkeypatch.setenv("SHOP_CATALOGUE_STATUS", "live")
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    order_limiter.reset()
    client = TestClient(create_app(f"sqlite:///{tmp_path / 'disabled.db'}", create_schema=True))
    assert client.post("/admin/seed-catalog").status_code == 200

    config = client.get("/v1/storefront/config").json()
    assert config["notifications"] == {"email": False, "from_email": None}

    order = _place(client)  # the order still goes through
    assert order["status"]["raw"] == "AWAITING_PAYMENT"
    order_id = _order_id(client, order["order_number"])
    assert _rows(client, order_id) == {mail_key(order_id, "placed"): ("SKIPPED", 1)}

    # A sweep leaves the skipped row alone: switching SMTP on does not mail the past.
    # The same sweep is where an expired pickup code loses its readable digits, so the
    # count of codes it forgot rides along with the mail counts.
    assert client.post("/v1/notifications/order-mail").json() == {
        "email": False, "considered": 0, "sent": 0, "skipped": 0, "failed": 0,
        "pickup_codes_forgotten": 0, "holds_released": 0,
    }


# --------------------------------------------------------------------------- configuration

def test_config_reads_the_environment_and_keeps_tls_on_by_default(monkeypatch):
    _clear_mail_env(monkeypatch)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("MAIL_FROM", "UA Market <shop@uamarket-fixture.ca>")
    monkeypatch.setenv("SHOP_CONTACT_EMAIL", "hello@uamarket-fixture.ca")
    config = mailer.load_config()
    assert config.enabled is True
    assert (config.port, config.security) == (587, "starttls")
    assert config.sender_email == "shop@uamarket-fixture.ca"
    assert config.reply_to == "hello@uamarket-fixture.ca"  # falls back to the shop contact address
    assert config.shop_name == "UA Market"
    assert "password" not in json.dumps(config.describe()).lower()

    monkeypatch.setenv("SMTP_PORT", "465")
    assert mailer.load_config().security == "ssl"

    monkeypatch.setenv("SMTP_SECURITY", "none")
    assert mailer.load_config().security == "none"

    monkeypatch.delenv("MAIL_FROM")
    assert mailer.load_config().enabled is False  # a host with no From address sends nothing


def test_message_carries_headers_and_both_parts(monkeypatch, transport):
    _clear_mail_env(monkeypatch)
    for key, value in SMTP_ENV.items():
        monkeypatch.setenv(key, value)

    result = mailer.send_email(to="buyer@example.test", subject="Order UA-260902-AAAA",
                               text="Total CA$ 10.00", html="<p>Total CA$ 10.00</p>")
    assert result.sent is True and result.error is None and result.message_id

    message = transport.last
    assert message["To"] == "buyer@example.test"
    assert message["From"] == "UA Market <shop@uamarket-fixture.ca>"
    assert message["Subject"] == "Order UA-260902-AAAA"
    assert message["Reply-To"] == "hello@uamarket-fixture.ca"
    assert message["Auto-Submitted"] == "auto-generated"
    assert transport.body().strip() == "Total CA$ 10.00"
    assert transport.html().strip() == "<p>Total CA$ 10.00</p>"


def test_header_injection_through_the_subject_is_flattened(monkeypatch, transport):
    _clear_mail_env(monkeypatch)
    for key, value in SMTP_ENV.items():
        monkeypatch.setenv(key, value)
    mailer.send_email(to="buyer@example.test", subject="Order\r\nBcc: someone@else.test", text="x")
    assert transport.last["Bcc"] is None
    assert transport.last["Subject"] == "Order Bcc: someone@else.test"


def test_smtp_transport_starts_tls_logs_in_and_never_logs_the_password(monkeypatch, caplog):
    _clear_mail_env(monkeypatch)
    for key, value in SMTP_ENV.items():
        monkeypatch.setenv(key, value)
    calls: list[tuple] = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            calls.append(("connect", host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            calls.append(("close",))
            return False

        def ehlo(self):
            calls.append(("ehlo",))

        def starttls(self, context=None):
            calls.append(("starttls", context is not None))

        def login(self, user, password):
            calls.append(("login", user, password))

        def send_message(self, message):
            calls.append(("send", message["To"]))

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(mailer, "TRANSPORT", None)
    with caplog.at_level(logging.DEBUG, logger="uamarket.mail"):
        result = mailer.send_email(to="buyer@example.test", subject="Order UA-1", text="Total CA$ 10.00")

    assert result.sent is True
    assert calls[0] == ("connect", "smtp.example.test", 587, 15.0)
    assert ("starttls", True) in calls
    assert ("login", "shop@uamarket-fixture.ca", SMTP_ENV["SMTP_PASSWORD"]) in calls
    assert ("send", "buyer@example.test") in calls
    assert SMTP_ENV["SMTP_PASSWORD"] not in caplog.text


def test_a_broken_mail_server_is_reported_and_never_raised(monkeypatch):
    _clear_mail_env(monkeypatch)
    for key, value in SMTP_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(mailer, "TRANSPORT", FakeTransport(error=smtplib.SMTPAuthenticationError(535, b"nope")))
    result = mailer.send_email(to="buyer@example.test", subject="Order UA-1", text="body")
    assert result.sent is False and result.disabled is False
    assert "SMTPAuthenticationError" in (result.error or "")


# --------------------------------------------------------------------------- content

def test_placed_email_states_the_order_the_customer_actually_made(shop, transport):
    order = _place(shop, qty=2)
    assert len(transport.messages) == 1
    message = transport.last
    body = transport.body()

    assert message["To"] == "buyer@example.test"
    assert order["order_number"] in message["Subject"]
    assert message["Subject"].startswith("UA Market ·")

    assert order["order_number"] in body
    assert order["lines"][0]["title"] in body
    assert order["lines"][0]["label"] in body  # the variant label, not just the product
    assert f"CA$ {order['totals']['total_cad']:,.2f}" in body
    assert "1 Main St" in body and "Ottawa" in body and "K1A 0B1" in body
    # the payment instruction that applies, and only that one
    assert "pay@uamarket-fixture.ca" in body
    assert "Interac e-Transfer" in body
    assert "card" not in body.lower()
    assert f"https://uamarket.example/order/{order['order_number']}" in body
    assert "Olena Buyer" in body
    assert transport.html().count(order["order_number"]) >= 1


def test_ukrainian_order_gets_a_ukrainian_email(shop, transport):
    order = _place(shop, locale="uk")
    body = transport.body()
    message = transport.last

    assert "Вітаємо, Olena Buyer!" in body
    assert "Ваше замовлення" in body and order["order_number"] in body
    assert "Разом" in body and "Товари" in body
    assert "Interac e-Transfer" in body and "pay@uamarket-fixture.ca" in body
    assert "Hello" not in body and "Items" not in body
    assert "замовлення" in message["Subject"]
    assert f"https://uamarket.example/uk/order/{order['order_number']}" in body
    # Ukrainian titles come from the catalogue, so the email names what the site named
    assert order["lines"][0]["title_uk"] in body


def test_payment_instruction_follows_the_order_and_paid_orders_ask_for_nothing():
    view = {
        "order_number": "UA-260902-TEST",
        "customer": {"name": "Buyer", "email": "buyer@example.test"},
        "fulfillment_method": "PICKUP",
        "ship_to": {},
        "lines": [{"qty": 1, "title": "Mug", "title_uk": "Горнятко", "label": "Small", "line_total_cad": 48.0}],
        "totals": {"subtotal_cad": 48.0, "shipping_cad": 0.0, "tax_cad": 6.24, "tax_rate": 0.13, "total_cad": 54.24},
        "status": {"label": "Awaiting payment", "label_uk": "Очікує оплати"},
        "payment": {"method": "STRIPE", "due": True, "amount_cad": 54.24, "checkout_url": "https://pay.example/session"},
        "tracking": None,
    }
    stripe_mail = mailer.render_order_email(view, kind="placed", lang="en", pickup_label="Locker pickup in Ottawa")
    assert "https://pay.example/session" in stripe_mail.text
    assert "Interac" not in stripe_mail.text
    assert "Locker pickup in Ottawa" in stripe_mail.text
    assert 'href="https://pay.example/session"' not in stripe_mail.html  # only the order link is linked

    invoice_view = view | {"payment": {"method": "INVOICE", "due": True, "amount_cad": 54.24, "contact_email": "hello@uamarket-fixture.ca"}}
    invoice_mail = mailer.render_order_email(invoice_view, kind="placed", lang="en")
    assert "hello@uamarket-fixture.ca" in invoice_mail.text
    assert "Interac" not in invoice_mail.text and "card" not in invoice_mail.text.lower()

    paid_view = view | {"payment": {"method": "STRIPE", "due": False},
                        "status": {"label": "Paid, preparing", "label_uk": "Оплачено, готуємо"},
                        "tracking": {"carrier": "Canada Post", "code": "TRACK123"}}
    paid_mail = mailer.render_order_email(paid_view, kind="paid", lang="uk")
    assert "більше нічого сплачувати" in paid_mail.text
    assert "Canada Post TRACK123" in paid_mail.text
    assert "оплату за замовлення UA-260902-TEST отримано" in paid_mail.subject

    with pytest.raises(ValueError):
        mailer.render_order_email(view, kind="shipped-somewhere", lang="en")


# --------------------------------------------------------------------------- the pipeline

def test_each_message_goes_out_once_and_payment_sends_the_second(shop, transport):
    order = _place(shop)
    order_id = _order_id(shop, order["order_number"])
    assert len(transport.messages) == 1
    assert _rows(shop, order_id) == {mail_key(order_id, "placed"): ("DELIVERED", 1)}

    # the same idempotency key comes back as the same order, and mails nothing twice
    repeat = shop.post("/v1/storefront/orders", json={
        "idempotency_key": order["idempotency_key"], "email": "buyer@example.test", "name": "Olena Buyer",
        "fulfillment_method": "SHIP",
        "ship_to": {"street1": "1 Main St", "city": "Ottawa", "province": "ON", "postal_code": "K1A 0B1"},
        "lines": [{"sku": order["variant"]["sku"], "qty": 1}],
    })
    assert repeat.status_code == 201 and repeat.json()["duplicate"] is True
    assert len(transport.messages) == 1

    assert shop.post(f"/v1/orders/{order_id}/mark-paid", json={"reference": "etransfer-1"}).status_code == 200
    assert len(transport.messages) == 2
    paid_body = transport.body()
    assert order["order_number"] in paid_body
    assert "Nothing is owed on this order." in paid_body
    assert "pay@uamarket-fixture.ca" not in paid_body  # a paid order is never asked to pay again

    shop.post(f"/v1/orders/{order_id}/mark-paid", json={})  # idempotent, and mails nothing
    assert len(transport.messages) == 2
    assert _rows(shop, order_id) == {
        mail_key(order_id, "placed"): ("DELIVERED", 1),
        mail_key(order_id, "paid"): ("DELIVERED", 1),
    }


def test_handoff_email_comes_from_the_sweep(shop, transport):
    order = _place(shop)
    order_id = _order_id(shop, order["order_number"])
    shop.post(f"/v1/orders/{order_id}/mark-paid", json={"reference": "etransfer-2"})
    assert len(transport.messages) == 2

    with shop.app.state.SessionLocal() as db:  # the warehouse side of the pipeline gets there
        row = db.get(Order, order_id)
        row.state = "HANDOFF_COMPLETE"
        db.commit()

    counts = shop.post("/v1/notifications/order-mail").json()
    assert counts == {"email": True, "considered": 1, "sent": 1, "skipped": 0, "failed": 0,
                      "pickup_codes_forgotten": 0, "holds_released": 0}
    assert len(transport.messages) == 3
    assert "with the courier" in transport.body()
    assert order["order_number"] in transport.last["Subject"]

    assert shop.post("/v1/notifications/order-mail").json()["sent"] == 0
    assert len(transport.messages) == 3


def test_a_failing_mail_server_never_breaks_an_order_and_is_retried(shop, monkeypatch):
    broken = FakeTransport(error=TimeoutError("connection timed out"))
    monkeypatch.setattr(mailer, "TRANSPORT", broken)

    order = _place(shop)  # the order is placed, the customer is served
    order_id = _order_id(shop, order["order_number"])
    assert order["status"]["raw"] == "AWAITING_PAYMENT"
    assert _rows(shop, order_id) == {mail_key(order_id, "placed"): ("PENDING", 1)}

    with shop.app.state.SessionLocal() as db:
        record = db.scalar(select(ExceptionRecord).where(ExceptionRecord.kind == "ORDER_EMAIL_FAILED",
                                                         ExceptionRecord.reference_id == order_id))
        assert record is not None and record.state == "OPEN"
        assert "TimeoutError" in record.details
        assert "buyer@example.test" in record.details

    working = FakeTransport()
    monkeypatch.setattr(mailer, "TRANSPORT", working)
    counts = shop.post("/v1/notifications/order-mail").json()
    assert counts["sent"] == 1 and counts["failed"] == 0
    assert len(working.messages) == 1
    assert _rows(shop, order_id) == {mail_key(order_id, "placed"): ("DELIVERED", 2)}


def test_repeated_failure_stops_and_leaves_one_open_exception(shop, monkeypatch):
    broken = FakeTransport(error=TimeoutError("connection timed out"))
    monkeypatch.setattr(mailer, "TRANSPORT", broken)
    order = _place(shop)
    order_id = _order_id(shop, order["order_number"])
    for _ in range(6):
        shop.post("/v1/notifications/order-mail")

    state, attempts = _rows(shop, order_id)[mail_key(order_id, "placed")]
    assert state == "FAILED" and attempts == MAIL_MAX_ATTEMPTS
    with shop.app.state.SessionLocal() as db:
        rows = list(db.scalars(select(ExceptionRecord).where(ExceptionRecord.kind == "ORDER_EMAIL_FAILED")))
    assert len(rows) == 1  # one problem, one row on the dashboard
    assert json.loads(rows[0].details)["stopped"] is True



def test_config_reports_the_address_customers_should_expect(shop):
    config = shop.get("/v1/storefront/config").json()
    assert config["notifications"] == {"email": True, "from_email": "shop@uamarket-fixture.ca"}
