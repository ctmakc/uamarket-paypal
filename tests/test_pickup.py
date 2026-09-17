"""Locker pickup, from the buyer's side.

The shop sells "collect it from the locker" at the checkout. These tests are about the
half of that promise the customer lives in: whether the method may be offered at all,
whether a code is ever minted, whether it reaches the person who bought the order and
nobody else, and whether it stops working when it should.

Nothing here touches a network: SMTP is a fake transport that keeps the message it was
handed, and the locker's edge device is the same HTTP event feed the courier tests use.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.orders import CUSTOMER_DOOR_REFUSED
from app.main import create_app
from app.models import Bay, ExceptionRecord, LockerAccess, Order, OutboxMessage, Variant
from app.services import locker, mailer
from app.services.ratelimit import lookup_limiter, order_limiter, reset_courier_guards
from app.services.storefront import mail_key

BAY = "BAY-CP"
EDGE = {"x-edge-token": "dev-edge-token"}
DEVICE = "LOCKER-PLC-01"
BUYER = "buyer@example.test"
OTHER_BUYER = "someone-else@example.test"

# A test fixture, not a fact about any building: the shop's real address is the owner's
# to give (docs/OWNER-ACTIONS.md).
ADDRESS = "12 Test Lane, Ottawa ON K1A 0B1"
HOURS = "Weekdays 09:00-20:00"
NOTE = "Second door on the left of the garage"

SMTP_ENV = {
    "SMTP_HOST": "smtp.example.test",
    "SMTP_PORT": "587",
    "SMTP_USER": "shop@uamarket-fixture.ca",
    "SMTP_PASSWORD": "s3cret-not-in-the-log",
    "MAIL_FROM": "UA Market <shop@uamarket-fixture.ca>",
    "SHOP_NAME": "UA Market",
}


class FakeTransport:
    """Stands in for the SMTP conversation and keeps every message it was given."""

    def __init__(self):
        self.messages = []

    def __call__(self, config, message):
        self.messages.append(message)

    def body(self, index: int = -1) -> str:
        return self.messages[index].get_body(preferencelist=("plain",)).get_content()

    def subjects(self) -> list[str]:
        return [m["Subject"] for m in self.messages]


@pytest.fixture()
def transport(monkeypatch):
    fake = FakeTransport()
    monkeypatch.setattr(mailer, "TRANSPORT", fake)
    return fake


@pytest.fixture()
def shop(tmp_path, monkeypatch):
    """A shop that has been told where its locker is, with e-Transfer and SMTP configured."""
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.setenv("ETRANSFER_EMAIL", "pay@uamarket-fixture.ca")
    # These tests exercise a shop selling its real catalogue; demo orders withhold payment details.
    monkeypatch.setenv("SHOP_CATALOGUE_STATUS", "live")
    monkeypatch.setenv("SHOP_CONTACT_EMAIL", "hello@uamarket-fixture.ca")
    monkeypatch.setenv("TAX_RATES_JSON", json.dumps({"ON": 0.13}))
    monkeypatch.setenv("PICKUP_ENABLED", "true")
    monkeypatch.setenv("PICKUP_ADDRESS", ADDRESS)
    monkeypatch.setenv("PICKUP_HOURS", HOURS)
    monkeypatch.setenv("PICKUP_NOTE", NOTE)
    monkeypatch.setenv("PICKUP_CODE_VALID_HOURS", "48")
    # A low work factor keeps the suite fast. Production default is 200 000 iterations.
    monkeypatch.setenv("LOCKER_PIN_KDF_ITERATIONS", "1000")
    for key, value in SMTP_ENV.items():
        monkeypatch.setenv(key, value)
    order_limiter.reset()
    lookup_limiter.reset()
    reset_courier_guards()
    client = TestClient(create_app(f"sqlite:///{tmp_path / 'pickup.db'}", create_schema=True))
    assert client.post("/admin/seed").status_code == 200          # bays, locations, devices
    assert client.post("/admin/seed-catalog").status_code == 200  # products with stock
    yield client
    reset_courier_guards()


# --------------------------------------------------------------------------- helpers


def _variant(client, slug: str = "opishnia-mug") -> dict:
    product = client.get(f"/v1/catalog/products/{slug}").json()
    healthy = [v for v in product["variants"] if v["availability"]["in_stock"] and not v["availability"]["low"]]
    return healthy[0] if healthy else next(v for v in product["variants"] if v["availability"]["in_stock"])


def place_pickup_order(client, *, email: str = BUYER, locale: str = "en", slug: str = "opishnia-mug") -> dict:
    variant = _variant(client, slug)
    payload = {
        "idempotency_key": f"pickup-{uuid.uuid4()}",
        "email": email,
        "name": "Olena Buyer",
        "locale": locale,
        "fulfillment_method": "PICKUP",
        "ship_to": None,
        "lines": [{"sku": variant["sku"], "qty": 1}],
    }
    response = client.post("/v1/storefront/orders", json=payload)
    assert response.status_code == 201, response.text
    return response.json() | {"variant": variant}


def order_id(client, number: str) -> str:
    with client.app.state.SessionLocal() as db:
        return db.scalar(select(Order.id).where(Order.order_number == number))


def barcode(client, sku: str) -> str:
    with client.app.state.SessionLocal() as db:
        return db.scalar(select(Variant.barcode).where(Variant.sku == sku))


def take_to_bay(client, order: dict, *, bay_id: str = BAY, label: str = "PICKUP-LOCAL-1") -> dict:
    """Pay, pick, pack, weigh, verify the label and put the parcel in a bay."""
    oid = order_id(client, order["order_number"])
    assert client.post(f"/v1/orders/{oid}/mark-paid", json={"reference": "etransfer-1"}).status_code == 200
    missions = client.post(f"/v1/orders/{oid}/reserve").json()["missions"]
    code = barcode(client, order["variant"]["sku"])
    for mission in missions:
        assert client.post(f"/v1/missions/{mission['id']}/scan-confirm", json={"barcode": code}).status_code == 200
    package_id = client.post(f"/v1/orders/{oid}/pack").json()["package_id"]
    assert client.post(f"/v1/packages/{package_id}/weight", json={"weight_g": 420}).status_code == 200
    assert client.post(f"/v1/packages/{package_id}/label-verify", json={
        "expected_label_code": label, "scanned_label_code": label,
    }).status_code == 200
    response = client.post(f"/v1/packages/{package_id}/assign-bay", json={"bay_id": bay_id})
    assert response.status_code == 200, response.text
    return response.json() | {"order_id": oid, "package_id": package_id}


def customer_view(client, order_number: str, email: str = BUYER):
    return client.get(f"/v1/storefront/orders/{order_number}", params={"email": email})


def verify_code(client, order_number: str, code: str):
    return client.post("/pickup/access/verify", json={"order_number": order_number, "pin": code})


def wrong_code(code: str, seed: int = 0) -> str:
    return f"{(int(code) + 1 + seed) % 1000000:06d}"


def edge_event(client, event_type: str, *, bay_id: str = BAY, command_id: str | None = None):
    r = client.post("/edge/events", headers=EDGE, json={
        "command_id": command_id, "device_id": DEVICE,
        "event_type": event_type, "payload": {"bay_id": bay_id},
    })
    assert r.status_code == 200, r.text


def complete_open_and_close(client, *, bay_id: str = BAY):
    """Walk the bay through the sensor events the edge would report for one opening."""
    unlock = next(m for m in client.get("/edge/commands", headers=EDGE).json()["commands"]
                  if m["event_type"] == "UNLOCK_BAY")
    edge_event(client, "LOCKER_UNLOCKED", bay_id=bay_id, command_id=unlock["id"])
    edge_event(client, "OUTER_DOOR_OPENED", bay_id=bay_id)
    edge_event(client, "OUTER_DOOR_CLOSED", bay_id=bay_id)
    edge_event(client, "LOCKER_LOCKED", bay_id=bay_id)


def access_rows(client, oid: str) -> list[LockerAccess]:
    with client.app.state.SessionLocal() as db:
        return list(db.scalars(select(LockerAccess).where(LockerAccess.order_id == oid)))


def open_exceptions(client, kind: str) -> list[ExceptionRecord]:
    with client.app.state.SessionLocal() as db:
        return list(db.scalars(select(ExceptionRecord).where(
            ExceptionRecord.kind == kind, ExceptionRecord.state == "OPEN")))


# --------------------------------------------------------------------------- the config gate


def test_pickup_is_not_offered_until_the_owner_says_where_the_locker_is(shop, monkeypatch):
    monkeypatch.delenv("PICKUP_ADDRESS", raising=False)
    monkeypatch.delenv("SHOP_PICKUP_ADDRESS_JSON", raising=False)
    config = shop.get("/v1/storefront/config").json()["pickup"]
    assert config["enabled"] is False
    assert config["switch_on"] is True and config["address_configured"] is False
    assert config["address"] is None

    variant = _variant(shop)
    refused = shop.post("/v1/storefront/orders", json={
        "idempotency_key": f"pickup-{uuid.uuid4()}", "email": BUYER, "name": "Olena Buyer",
        "fulfillment_method": "PICKUP", "ship_to": None,
        "lines": [{"sku": variant["sku"], "qty": 1}],
    })
    assert refused.status_code == 400, refused.text
    assert refused.json()["detail"]["code"] == "fulfillment_method"

    # The switch alone is not enough either way round: an address with the switch off is off.
    monkeypatch.setenv("PICKUP_ADDRESS", ADDRESS)
    monkeypatch.setenv("PICKUP_ENABLED", "false")
    assert shop.get("/v1/storefront/config").json()["pickup"]["enabled"] is False

    monkeypatch.setenv("PICKUP_ENABLED", "true")
    live = shop.get("/v1/storefront/config").json()["pickup"]
    assert live["enabled"] is True
    assert live["address"] == ADDRESS and live["hours"] == HOURS and live["note"] == NOTE
    assert live["code_valid_hours"] == 48
    assert place_pickup_order(shop)["order_number"].startswith("UA-")


def test_a_parcel_that_reaches_a_bay_without_an_address_leaves_an_exception_and_no_code(shop, monkeypatch, transport):
    order = place_pickup_order(shop)
    monkeypatch.delenv("PICKUP_ADDRESS", raising=False)
    monkeypatch.delenv("SHOP_PICKUP_ADDRESS_JSON", raising=False)
    assigned = take_to_bay(shop, order)

    assert "customer_pickup" not in assigned
    assert access_rows(shop, assigned["order_id"]) == []
    rows = open_exceptions(shop, "PICKUP_NOT_CONFIGURED")
    assert len(rows) == 1 and rows[0].reference_id == assigned["order_id"]
    assert "PICKUP_ADDRESS" in rows[0].details
    assert not any("locker" in s for s in transport.subjects())

    view = customer_view(shop, order["order_number"]).json()["pickup"]
    assert view["code"] is None and view["address"] is None
    assert "not published" in view["message"]


# --------------------------------------------------------------------------- minting and mail


def test_the_bay_assignment_mints_a_code_and_builds_the_email(shop, transport):
    order = place_pickup_order(shop)
    before = datetime.now(timezone.utc)
    assigned = take_to_bay(shop, order)

    handed_back = assigned["customer_pickup"]
    code = handed_back["code"]
    assert code.isdigit() and len(code) == 6
    assert handed_back["bay_id"] == BAY and handed_back["emailed"] is True

    rows = access_rows(shop, assigned["order_id"])
    assert len(rows) == 1
    row = rows[0]
    assert row.kind == "CUSTOMER" and row.pickup_id is None and row.bay_id == BAY
    assert row.used_at is None and row.revoked_at is None
    # Stored the way a courier PIN is stored: salted PBKDF2, never the digits themselves.
    assert row.pin_hash.startswith("p2$") and code not in row.pin_hash
    assert locker.verify_pin(code, row.pin_hash) is True
    assert locker.verify_pin(wrong_code(code), row.pin_hash) is False
    # 48 hours, as PICKUP_CODE_VALID_HOURS says.
    valid_until = row.valid_until if row.valid_until.tzinfo else row.valid_until.replace(tzinfo=timezone.utc)
    assert timedelta(hours=47) < valid_until - before < timedelta(hours=49)

    # placed, paid, and now the fourth message.
    assert len(transport.messages) == 3
    body = transport.body()
    assert transport.messages[-1]["Subject"] == f"UA Market · order {order['order_number']} is in the locker"
    for fact in (order["order_number"], ADDRESS, HOURS, NOTE, BAY, code):
        assert fact in body, fact
    assert "opens the bay once" in body
    assert "UTC" in body  # the hour the code stops working, in a zone it names

    with shop.app.state.SessionLocal() as db:
        row = db.scalar(select(OutboxMessage).where(
            OutboxMessage.idempotency_key == mail_key(assigned["order_id"], "pickup_ready")))
        assert row is not None and row.state == "DELIVERED"
        # The outbox is read by operators and by the edge, so the code stays out of it.
        codes = db.scalars(select(OutboxMessage.payload_json).where(
            OutboxMessage.event_type == "PICKUP_CODE_ISSUED"))
        for payload in codes:
            assert code not in payload


def test_the_ukrainian_buyer_is_written_to_in_ukrainian(shop, transport):
    order = place_pickup_order(shop, locale="uk")
    assigned = take_to_bay(shop, order)
    body = transport.body()
    assert "Замовлення" in body and "у локері" in body
    assert "Одноразовий код" in body and assigned["customer_pickup"]["code"] in body
    assert ADDRESS in body
    assert "One-time code" not in body


def test_the_same_order_and_bay_never_leave_the_buyer_holding_two_codes(shop, transport):
    order = place_pickup_order(shop)
    assigned = take_to_bay(shop, order)
    code = assigned["customer_pickup"]["code"]
    sent = len(transport.messages)

    with shop.app.state.SessionLocal() as db:
        row = db.get(Order, assigned["order_id"])
        again = locker.issue_customer_access(db, order=row, bay_id=BAY)
        assert again.display_code == code  # the live credential, not a second one
        db.commit()
    assert len(access_rows(shop, assigned["order_id"])) == 1

    # A parcel moved to another bay is a different matter: the old code is withdrawn and
    # the buyer is given one that opens the bay their parcel is actually in.
    with shop.app.state.SessionLocal() as db:
        row = db.get(Order, assigned["order_id"])
        moved = locker.issue_customer_access(db, order=row, bay_id="BAY-OTHER")
        db.commit()
        assert moved.display_code != code and moved.bay_id == "BAY-OTHER"
    rows = {r.bay_id: r for r in access_rows(shop, assigned["order_id"])}
    assert rows[BAY].revoked_at is not None and rows[BAY].display_code is None
    assert rows[BAY].revoked_reason == "PARCEL_MOVED_TO_ANOTHER_BAY"
    assert verify_code(shop, order["order_number"], code).status_code == 403
    assert len(transport.messages) == sent  # nothing is emailed from inside the service

    view = customer_view(shop, order["order_number"]).json()["pickup"]
    assert view["bay"] == "BAY-OTHER" and view["code"] == moved.display_code


def test_without_smtp_the_code_still_reaches_the_customer(shop, monkeypatch, transport):
    for key in ("SMTP_HOST", "MAIL_FROM"):
        monkeypatch.delenv(key, raising=False)
    order = place_pickup_order(shop)
    assigned = take_to_bay(shop, order)
    code = assigned["customer_pickup"]["code"]

    assert transport.messages == []            # the mailer stays disabled, exactly as before
    assert assigned["customer_pickup"]["emailed"] is False
    with shop.app.state.SessionLocal() as db:
        row = db.scalar(select(OutboxMessage).where(
            OutboxMessage.idempotency_key == mail_key(assigned["order_id"], "pickup_ready")))
        assert row is not None and row.state == "SKIPPED"

    # The order page is the channel that is left, and it carries everything the mail would.
    view = customer_view(shop, order["order_number"]).json()["pickup"]
    assert view["code"] == code and view["bay"] == BAY
    assert view["address"] == ADDRESS and view["hours"] == HOURS
    assert view["state"] == "ready" and view["valid_until"] and view["valid_until_text"]


# --------------------------------------------------------------------------- who may read it


def test_the_code_is_on_the_buyers_own_page_and_on_nobody_elses(shop, transport):
    mine = place_pickup_order(shop)
    theirs = place_pickup_order(shop, email=OTHER_BUYER, slug="greeting-cards")
    assigned = take_to_bay(shop, mine)
    code = assigned["customer_pickup"]["code"]

    mine_view = customer_view(shop, mine["order_number"]).json()
    assert mine_view["pickup"]["code"] == code
    assert mine_view["status"]["key"] == "ready"
    assert mine_view["status"]["label"] == "In the locker, waiting for you"

    # The other customer's own page names no code at all: their parcel is not in a bay.
    theirs_view = customer_view(shop, theirs["order_number"], email=OTHER_BUYER).json()
    assert theirs_view["pickup"]["code"] is None
    assert theirs_view["pickup"]["state"] == "preparing"
    assert code not in json.dumps(theirs_view)

    # And they cannot read my order at all, with or without the right order number.
    assert customer_view(shop, mine["order_number"], email=OTHER_BUYER).status_code == 404
    assert customer_view(shop, mine["order_number"], email="").status_code == 404


def test_before_a_code_exists_the_page_says_what_happens_next(shop):
    order = place_pickup_order(shop)
    view = customer_view(shop, order["order_number"]).json()["pickup"]
    assert view["state"] == "preparing"
    assert view["code"] is None and view["bay"] is None
    assert view["valid_until"] is None and view["valid_until_text"] is None
    assert view["address"] == ADDRESS and view["valid_hours"] == 48
    assert "when your parcel is in the locker" in view["message"]
    assert "щойно посилка буде в локері" in view["message_uk"]


# --------------------------------------------------------------------------- guessing


def test_wrong_codes_are_locked_out_and_an_operator_can_lift_it(shop, monkeypatch):
    monkeypatch.setenv("COURIER_PIN_MAX_FAILURES", "3")
    order = place_pickup_order(shop)
    assigned = take_to_bay(shop, order)
    code = assigned["customer_pickup"]["code"]
    number = order["order_number"]

    for i in range(3):
        assert verify_code(shop, number, wrong_code(code, i)).status_code == 403

    locked = verify_code(shop, number, code)
    assert locked.status_code == 429, locked.text
    assert int(locked.headers["retry-after"]) > 0

    rows = open_exceptions(shop, "CUSTOMER_PIN_LOCKOUT")
    assert len(rows) == 1 and rows[0].reference_id == number
    details = json.loads(rows[0].details)
    assert details["failed_attempts"] == 3
    assert details["unlock_endpoint"] == f"/v1/pickup-access/{number}/unlock"
    # One exception per lockout, not one per rejected attempt.
    assert verify_code(shop, number, code).status_code == 429
    assert len(open_exceptions(shop, "CUSTOMER_PIN_LOCKOUT")) == 1

    unlock = shop.post(f"/v1/pickup-access/{number}/unlock")
    assert unlock.status_code == 200, unlock.text
    assert unlock.json()["unlocked"] is True
    assert unlock.json()["cleared_client_ips"] == ["testclient"]
    assert open_exceptions(shop, "CUSTOMER_PIN_LOCKOUT") == []
    assert verify_code(shop, number, code).status_code == 200


def test_a_flood_of_attempts_is_capped_and_an_unknown_order_tells_a_guesser_nothing(shop, monkeypatch):
    monkeypatch.setenv("COURIER_PIN_MAX_FAILURES", "500")
    monkeypatch.setenv("COURIER_PIN_IP_MAX_FAILURES", "500")
    monkeypatch.setenv("COURIER_PIN_ATTEMPTS_PER_WINDOW", "5")
    codes = [verify_code(shop, "UA-260903-ZZZZ", f"{i:06d}").status_code for i in range(7)]
    assert codes == [403] * 5 + [429, 429]
    assert shop.post("/v1/pickup-access/UA-260903-ZZZZ/unlock").status_code == 404


def test_guessing_an_order_number_locks_the_address_out(shop, monkeypatch):
    monkeypatch.setenv("COURIER_PIN_MAX_FAILURES", "500")
    monkeypatch.setenv("COURIER_PIN_IP_MAX_FAILURES", "3")
    for i in range(3):
        assert verify_code(shop, f"UA-260903-A{i:03d}", "000000").status_code == 403
    order = place_pickup_order(shop)
    assigned = take_to_bay(shop, order)
    blocked = verify_code(shop, order["order_number"], assigned["customer_pickup"]["code"])
    assert blocked.status_code == 429
    assert len(open_exceptions(shop, "CUSTOMER_PIN_IP_LOCKOUT")) == 1


# --------------------------------------------------------------------------- the code dies


def test_the_code_opens_the_bay_once(shop, transport):
    order = place_pickup_order(shop)
    assigned = take_to_bay(shop, order)
    code = assigned["customer_pickup"]["code"]

    opened = verify_code(shop, order["order_number"], code)
    assert opened.status_code == 200, opened.text
    assert opened.json() == {"ok": True, "bay_id": BAY, "outer_door_locked": True}

    # A second try with the same code is refused, and the page stops printing it. The
    # refusal says the same thing every refusal at this door says; the reason a code was
    # turned away is the shop's business and stays in the log.
    second = verify_code(shop, order["order_number"], code)
    assert second.status_code == 403 and second.json()["detail"] == CUSTOMER_DOOR_REFUSED
    view = customer_view(shop, order["order_number"]).json()["pickup"]
    assert view["state"] == "opened" and view["code"] is None
    with shop.app.state.SessionLocal() as db:
        row = db.scalar(select(LockerAccess).where(LockerAccess.order_id == assigned["order_id"]))
        assert row.used_at is not None and row.display_code is None

    # The buyer emptying the bay is a handoff the operator can complete.
    complete_open_and_close(shop)
    assert shop.post(f"/v1/bays/{BAY}/handoff").status_code == 200
    done = customer_view(shop, order["order_number"]).json()
    assert done["status"]["key"] == "collected" and done["status"]["label"] == "Collected"
    assert done["pickup"]["state"] == "collected" and done["pickup"]["code"] is None


def test_the_code_stops_working_when_the_parcel_leaves_the_bay(shop, transport):
    order = place_pickup_order(shop)
    assigned = take_to_bay(shop, order)
    code = assigned["customer_pickup"]["code"]

    # The parcel leaves in a courier's hands instead: the buyer's code opens nothing after that.
    now = datetime.now(timezone.utc)
    pickup = shop.post("/v1/pickups", json={
        "carrier": "Canada Post", "bay_id": BAY,
        "window_start": (now - timedelta(minutes=5)).isoformat(),
        "window_end": (now + timedelta(hours=1)).isoformat(),
    }).json()
    assert shop.post("/courier/access/verify", json={"pickup_id": pickup["pickup_id"], "pin": pickup["pin"]}).status_code == 200
    complete_open_and_close(shop)
    assert shop.post(f"/v1/bays/{BAY}/handoff").status_code == 200

    refused = verify_code(shop, order["order_number"], code)
    assert refused.status_code == 403 and refused.json()["detail"] == CUSTOMER_DOOR_REFUSED
    with shop.app.state.SessionLocal() as db:
        row = db.scalar(select(LockerAccess).where(LockerAccess.order_id == assigned["order_id"]))
        assert row.revoked_at is not None and row.display_code is None
        assert row.revoked_reason == "PARCEL_LEFT_THE_BAY"
    view = customer_view(shop, order["order_number"]).json()["pickup"]
    assert view["state"] == "collected" and view["code"] is None


def test_a_code_past_its_hours_opens_nothing_and_the_page_says_so(shop, transport):
    order = place_pickup_order(shop)
    assigned = take_to_bay(shop, order)
    code = assigned["customer_pickup"]["code"]
    with shop.app.state.SessionLocal() as db:
        row = db.scalar(select(LockerAccess).where(LockerAccess.order_id == assigned["order_id"]))
        row.valid_until = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()

    expired = verify_code(shop, order["order_number"], code)
    assert expired.status_code == 403 and expired.json()["detail"] == CUSTOMER_DOOR_REFUSED
    view = customer_view(shop, order["order_number"]).json()["pickup"]
    assert view["state"] == "expired" and view["code"] is None
    assert "Write to the shop" in view["message"]
    # And nothing tries to send a "your parcel is in the locker" email for it any more.
    assert shop.post("/v1/notifications/order-mail").json()["considered"] == 0


# --------------------------------------------------------------------------- the two doors


def test_the_courier_path_still_works_and_the_two_credentials_never_cross(shop):
    order = place_pickup_order(shop)
    assigned = take_to_bay(shop, order)
    customer_code = assigned["customer_pickup"]["code"]

    now = datetime.now(timezone.utc)
    pickup = shop.post("/v1/pickups", json={
        "carrier": "Canada Post", "bay_id": BAY,
        "window_start": (now - timedelta(minutes=5)).isoformat(),
        "window_end": (now + timedelta(hours=1)).isoformat(),
    }).json()
    courier_pin = pickup["pin"]
    assert courier_pin != customer_code

    # The buyer's code is not a courier PIN...
    crossed = shop.post("/courier/access/verify", json={"pickup_id": pickup["pickup_id"], "pin": customer_code})
    assert crossed.status_code == 403
    # ...and the courier's PIN is not the buyer's code.
    assert verify_code(shop, order["order_number"], courier_pin).status_code == 403
    # Neither failed attempt spent anything: both doors still open for their own holder.
    assert shop.post("/courier/access/verify", json={"pickup_id": pickup["pickup_id"], "pin": courier_pin}).status_code == 200
    with shop.app.state.SessionLocal() as db:
        rows = {r.kind: r for r in db.scalars(select(LockerAccess))}
        assert set(rows) == {"COURIER", "CUSTOMER"}
        assert rows["COURIER"].used_at is not None and rows["COURIER"].order_id is None
        assert rows["CUSTOMER"].used_at is None and rows["CUSTOMER"].pickup_id is None


def test_a_courier_pickup_alone_still_opens_and_closes_a_bay(shop):
    """The courier flow with no web pickup order anywhere near it."""
    now = datetime.now(timezone.utc)
    pickup = shop.post("/v1/pickups", json={
        "carrier": "Canada Post", "bay_id": "BAY-OTHER",
        "window_start": (now - timedelta(minutes=5)).isoformat(),
        "window_end": (now + timedelta(hours=1)).isoformat(),
    }).json()
    assert shop.post("/courier/access/verify", json={"pickup_id": pickup["pickup_id"], "pin": pickup["pin"]}).status_code == 200
    assert shop.post("/v1/bays/BAY-OTHER/handoff").status_code == 409  # door state comes from the edge
    complete_open_and_close(shop, bay_id="BAY-OTHER")
    assert shop.post("/v1/bays/BAY-OTHER/handoff").status_code == 200
    with shop.app.state.SessionLocal() as db:
        assert db.get(Bay, "BAY-OTHER").outer_door_locked is True
