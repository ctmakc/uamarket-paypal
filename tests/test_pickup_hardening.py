"""The locker pickup loop under an adversary, and the six defects that were found in it.

Each test here is named after the thing that was wrong before it was fixed. They lean on
the helpers of tests/test_pickup.py — same shop, same fake SMTP transport, same walk from
the checkout to a parcel in a bay — so this file holds only what is new:

1. a parcel already in a bay can be given a fresh code (five surfaces promised it, and
   nothing in the API could do it);
2. the buyer's door answers every failure with one body, so it stops being an oracle for
   order numbers;
3. a disabled mailer keeps the one-time code out of the application log;
4. `X-Forwarded-For` is read only from a proxy the owner has named, and both doors and the
   storefront limiters read the address the same way;
5. a structured address with no street does not open the pickup gate;
6. a quote for a method the shop refuses is priced as shipping, and an expired credential
   keeps no readable digits.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.api import orders as orders_api
from app.api import storefront as storefront_api
from app.models import LockerAccess, OutboxMessage
from app.services import locker
from app.services.ratelimit import client_address, reset_courier_guards, trusted_proxies
from app.services.storefront import mail_key

# The pickup suite is the fixture library for this one: `shop` builds a configured shop
# with a fake SMTP transport, and the helpers walk an order from the checkout into a bay.
from tests.test_pickup import (  # noqa: F401  (shop and transport are fixtures)
    ADDRESS, BAY, BUYER, HOURS, OTHER_BUYER,
    _variant, access_rows, barcode, customer_view, open_exceptions, order_id,
    place_pickup_order, shop, take_to_bay, transport, verify_code, wrong_code,
)

REISSUE = "/v1/packages/{}/pickup-code"


def expire_the_code(client, oid: str, minutes: int = 1) -> None:
    """Wind the credential's last hour into the past, the way waiting three days would."""
    with client.app.state.SessionLocal() as db:
        row = db.scalar(select(LockerAccess).where(
            LockerAccess.order_id == oid, LockerAccess.revoked_at.is_(None)))
        row.valid_until = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        db.commit()


def place_ship_order(client, *, email: str = BUYER, slug: str = "greeting-cards") -> dict:
    variant = _variant(client, slug)
    response = client.post("/v1/storefront/orders", json={
        "idempotency_key": f"ship-{uuid.uuid4()}",
        "email": email,
        "name": "Olena Buyer",
        "fulfillment_method": "SHIP",
        "ship_to": {"name": "Olena Buyer", "street1": "12 Test Lane", "city": "Ottawa",
                    "province": "ON", "postal_code": "K1A 0B1", "country": "CA"},
        "lines": [{"sku": variant["sku"], "qty": 1}],
    })
    assert response.status_code == 201, response.text
    return response.json() | {"variant": variant}


def pack_without_a_bay(client, order: dict) -> str:
    """Everything take_to_bay does, stopping one step before the parcel goes into a bay."""
    oid = order_id(client, order["order_number"])
    assert client.post(f"/v1/orders/{oid}/mark-paid", json={"reference": "etransfer-1"}).status_code == 200
    missions = client.post(f"/v1/orders/{oid}/reserve").json()["missions"]
    code = barcode(client, order["variant"]["sku"])
    for mission in missions:
        assert client.post(f"/v1/missions/{mission['id']}/scan-confirm", json={"barcode": code}).status_code == 200
    package_id = client.post(f"/v1/orders/{oid}/pack").json()["package_id"]
    assert client.post(f"/v1/packages/{package_id}/weight", json={"weight_g": 420}).status_code == 200
    return package_id


def live_row(client, oid: str) -> LockerAccess | None:
    with client.app.state.SessionLocal() as db:
        return locker.live_customer_access(db, oid)


class FakeRequest:
    """The two attributes `client_address` reads off a Starlette request."""

    class _Peer:
        def __init__(self, host: str):
            self.host = host

    def __init__(self, peer: str | None, forwarded: str | None = None):
        self.client = FakeRequest._Peer(peer) if peer else None
        self.headers = {"x-forwarded-for": forwarded} if forwarded else {}


# ------------------------------------------------- 1. a code that can be re-issued


def test_a_parcel_already_in_a_bay_can_be_given_a_fresh_code(shop, transport):
    order = place_pickup_order(shop)
    assigned = take_to_bay(shop, order)
    old_code = assigned["customer_pickup"]["code"]
    expire_the_code(shop, assigned["order_id"])
    sent = len(transport.messages)

    # The route the five surfaces were promising. Assigning the bay again is refused,
    # because the parcel is already in it — which is the whole reason this exists.
    again = shop.post(f"/v1/packages/{assigned['package_id']}/assign-bay", json={"bay_id": BAY})
    assert again.status_code == 409

    fresh = shop.post(REISSUE.format(assigned["package_id"]))
    assert fresh.status_code == 200, fresh.text
    body = fresh.json()
    assert body["bay_id"] == BAY and body["state"] == "READY_FOR_PICKUP"
    handed_back = body["customer_pickup"]
    new_code = handed_back["code"]
    assert new_code.isdigit() and len(new_code) == 6 and new_code != old_code
    assert handed_back["order_number"] == order["order_number"]
    assert handed_back["bay_id"] == BAY and handed_back["emailed"] is True
    assert datetime.fromisoformat(handed_back["valid_until"]) > datetime.now(timezone.utc)

    # The old credential is withdrawn and carries no digits; the new one is the live one.
    rows = sorted(access_rows(shop, assigned["order_id"]), key=lambda r: r.valid_until)
    assert len(rows) == 2
    assert rows[0].revoked_at is not None and rows[0].display_code is None
    assert rows[0].revoked_reason == "CODE_REISSUED"
    assert rows[1].display_code == new_code and rows[1].revoked_at is None

    # The door takes the new code and refuses the old one.
    assert verify_code(shop, order["order_number"], old_code).status_code == 403
    assert verify_code(shop, order["order_number"], new_code).status_code == 200

    # The buyer is written to again, and the page carries the new code either way.
    assert len(transport.messages) == sent + 1
    assert new_code in transport.body() and old_code not in transport.body()
    assert transport.messages[-1]["Subject"].endswith("is in the locker")


def test_the_reissued_code_reaches_the_page_and_the_outbox_records_the_second_message(shop, transport):
    order = place_pickup_order(shop)
    assigned = take_to_bay(shop, order)
    expire_the_code(shop, assigned["order_id"])
    view = customer_view(shop, order["order_number"]).json()["pickup"]
    assert view["state"] == "expired" and view["code"] is None

    fresh = shop.post(REISSUE.format(assigned["package_id"])).json()["customer_pickup"]
    view = customer_view(shop, order["order_number"]).json()["pickup"]
    assert view["state"] == "ready" and view["code"] == fresh["code"]
    assert view["bay"] == BAY and view["address"] == ADDRESS

    with shop.app.state.SessionLocal() as db:
        row = db.scalar(select(OutboxMessage).where(
            OutboxMessage.idempotency_key == mail_key(assigned["order_id"], "pickup_ready")))
        # Claimed again and delivered again: one row per message, not a second one.
        assert row.state == "DELIVERED" and row.attempt_count == 1
        # The code itself never enters the outbox, this time either.
        for payload in db.scalars(select(OutboxMessage.payload_json)):
            assert fresh["code"] not in payload


def test_a_fresh_code_is_refused_for_a_parcel_that_is_not_in_a_bay_and_for_a_shipped_order(shop, transport):
    # Packed and weighed, but never assigned to a bay.
    order = place_pickup_order(shop)
    package_id = pack_without_a_bay(shop, order)
    refused = shop.post(REISSUE.format(package_id))
    assert refused.status_code == 409 and "not in a bay" in refused.json()["detail"]
    assert access_rows(shop, order_id(shop, order["order_number"])) == []

    # A parcel that is in a bay for an order nobody chose to collect.
    shipped = place_ship_order(shop)
    assigned = take_to_bay(shop, shipped, bay_id="BAY-OTHER")
    assert "customer_pickup" not in assigned
    wrong_method = shop.post(REISSUE.format(assigned["package_id"]))
    assert wrong_method.status_code == 409 and "locker pickup" in wrong_method.json()["detail"]
    assert access_rows(shop, assigned["order_id"]) == []

    assert shop.post(REISSUE.format("no-such-package")).status_code == 404


def test_a_fresh_code_is_refused_while_the_shop_has_no_address(shop, monkeypatch, transport):
    order = place_pickup_order(shop)
    assigned = take_to_bay(shop, order)
    monkeypatch.delenv("PICKUP_ADDRESS", raising=False)
    monkeypatch.delenv("SHOP_PICKUP_ADDRESS_JSON", raising=False)
    refused = shop.post(REISSUE.format(assigned["package_id"]))
    assert refused.status_code == 409 and "PICKUP_ADDRESS" in refused.json()["detail"]
    # The code that already existed is untouched: the failed re-issue withdrew nothing.
    assert live_row(shop, assigned["order_id"]) is not None


def test_a_parcel_that_waited_for_the_address_gets_its_code_and_closes_the_alert(shop, monkeypatch, transport):
    """The recovery the exception row asks for, which had no route until now."""
    order = place_pickup_order(shop)
    monkeypatch.delenv("PICKUP_ADDRESS", raising=False)
    monkeypatch.delenv("SHOP_PICKUP_ADDRESS_JSON", raising=False)
    assigned = take_to_bay(shop, order)
    assert "customer_pickup" not in assigned
    assert len(open_exceptions(shop, "PICKUP_NOT_CONFIGURED")) == 1

    monkeypatch.setenv("PICKUP_ADDRESS", ADDRESS)
    fresh = shop.post(REISSUE.format(assigned["package_id"]))
    assert fresh.status_code == 200, fresh.text
    code = fresh.json()["customer_pickup"]["code"]
    assert open_exceptions(shop, "PICKUP_NOT_CONFIGURED") == []
    assert verify_code(shop, order["order_number"], code).status_code == 200
    assert ADDRESS in transport.body()


# ------------------------------------------------- 2. the door stops being an oracle


def _door_bodies(client, cases: list[tuple[str, str]]) -> list[str]:
    out = []
    for number, code in cases:
        response = verify_code(client, number, code)
        assert response.status_code == 403, (number, response.text)
        out.append(json.dumps(response.json(), sort_keys=True))
    return out


def test_the_buyers_door_answers_every_failure_with_one_body(shop, monkeypatch, transport, caplog):
    monkeypatch.setenv("COURIER_PIN_MAX_FAILURES", "500")
    monkeypatch.setenv("COURIER_PIN_IP_MAX_FAILURES", "500")
    monkeypatch.setenv("COURIER_PIN_ATTEMPTS_PER_WINDOW", "500")

    live = place_pickup_order(shop)
    live_assigned = take_to_bay(shop, live)
    live_code = live_assigned["customer_pickup"]["code"]

    used = place_pickup_order(shop, email=OTHER_BUYER, slug="greeting-cards")
    used_assigned = take_to_bay(shop, used, bay_id="BAY-OTHER")
    used_code = used_assigned["customer_pickup"]["code"]
    assert verify_code(shop, used["order_number"], used_code).status_code == 200

    expired = place_pickup_order(shop, slug="opishnia-bowl-set")
    expired_assigned = take_to_bay(shop, expired, bay_id=BAY, label="PICKUP-LOCAL-2")
    expired_code = expired_assigned["customer_pickup"]["code"]
    expire_the_code(shop, expired_assigned["order_id"])

    shipped = place_ship_order(shop, slug="enamel-pin-set")

    with caplog.at_level(logging.INFO, logger="uamarket.pickup"):
        bodies = _door_bodies(shop, [
            ("UA-260903-ZZZZ", "000000"),                    # no such order at all
            (live["order_number"], wrong_code(live_code)),   # real order, wrong code
            (used["order_number"], used_code),               # a code already spent
            (expired["order_number"], expired_code),         # a code past its hours
            (shipped["order_number"], "000000"),             # an order nobody may collect
        ])
    assert len(set(bodies)) == 1, bodies
    only = json.loads(bodies[0])["detail"]
    assert only == orders_api.CUSTOMER_DOOR_REFUSED
    # The one sentence names no order, no code and no reason. It does say what a customer
    # whose code ran out should do, and it says it to everybody, so it separates nobody.
    for leak in ("credential", "already used", "withdrawn", "outside its validity", "Invalid code"):
        assert leak.lower() not in only.lower()
    for secret in (live["order_number"], used["order_number"], expired["order_number"],
                   shipped["order_number"], live_code, used_code, expired_code):
        assert secret not in only

    # The reason is kept where the shop can read it and the caller cannot.
    for reason in ("No access credential", "Invalid code", "Code already used",
                   "Code outside its validity window"):
        assert reason in caplog.text
    assert live["order_number"] in caplog.text

    # And it survives into the exception the lockout writes.
    reset_courier_guards()
    monkeypatch.setenv("COURIER_PIN_MAX_FAILURES", "2")
    for i in range(2):
        assert verify_code(shop, live["order_number"], wrong_code(live_code, i + 5)).status_code == 403
    rows = open_exceptions(shop, "CUSTOMER_PIN_LOCKOUT")
    assert len(rows) == 1
    assert json.loads(rows[0].details)["last_failure"] == "Invalid code"


def test_the_courier_door_still_says_what_a_courier_needs_to_hear(shop):
    """A documented decision: the courier is at the locker and the message helps them."""
    now = datetime.now(timezone.utc)
    pickup = shop.post("/v1/pickups", json={
        "carrier": "Canada Post", "bay_id": BAY,
        "window_start": (now + timedelta(hours=2)).isoformat(),
        "window_end": (now + timedelta(hours=4)).isoformat(),
    }).json()
    early = shop.post("/courier/access/verify", json={"pickup_id": pickup["pickup_id"], "pin": pickup["pin"]})
    assert early.status_code == 403 and "outside pickup window" in early.json()["detail"]
    unknown = shop.post("/courier/access/verify", json={"pickup_id": "nope", "pin": "000000"})
    assert unknown.json()["detail"] == "No access credential"


# ------------------------------------------------- 3. the code stays out of the log


def test_a_disabled_mailer_keeps_the_one_time_code_out_of_the_log(shop, monkeypatch, caplog):
    for key in ("SMTP_HOST", "MAIL_FROM"):
        monkeypatch.delenv(key, raising=False)
    order = place_pickup_order(shop)
    with caplog.at_level(logging.INFO, logger="uamarket.mail"):
        assigned = take_to_bay(shop, order)
    code = assigned["customer_pickup"]["code"]

    assert code not in caplog.text
    # What an operator does get: who it was for, what it said on the tin, how long it was.
    assert BUYER in caplog.text
    assert "is in the locker" in caplog.text
    assert "body_length" in caplog.text
    assert ADDRESS not in caplog.text  # the body itself is off by default


def test_the_body_log_flag_prints_the_message_and_still_redacts_the_code(shop, monkeypatch, caplog):
    for key in ("SMTP_HOST", "MAIL_FROM"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("MAIL_LOG_BODIES", "true")
    order = place_pickup_order(shop)
    with caplog.at_level(logging.INFO, logger="uamarket.mail"):
        assigned = take_to_bay(shop, order)
    code = assigned["customer_pickup"]["code"]

    assert code not in caplog.text
    # The rest of the message is readable, which is what the flag is for.
    assert ADDRESS in caplog.text and HOURS in caplog.text
    assert order["order_number"] in caplog.text
    assert "One-time code" in caplog.text  # the line is there, the digits are not


# ------------------------------------------------- 4. one reading of the client address


def test_x_forwarded_for_is_ignored_unless_the_owner_named_the_proxy(monkeypatch):
    monkeypatch.delenv("TRUSTED_PROXY_IPS", raising=False)
    assert trusted_proxies() == frozenset()
    spoofed = FakeRequest("10.0.0.9", "1.2.3.4")
    assert client_address(spoofed) == "10.0.0.9"

    monkeypatch.setenv("TRUSTED_PROXY_IPS", "10.0.0.9, 10.0.0.10")
    assert client_address(spoofed) == "1.2.3.4"
    # The last hop that is not itself a named proxy is the caller.
    assert client_address(FakeRequest("10.0.0.9", "8.8.8.8, 1.2.3.4, 10.0.0.10")) == "1.2.3.4"
    # A chain that is nothing but our own proxies names nobody, so the peer stands.
    assert client_address(FakeRequest("10.0.0.9", "10.0.0.10")) == "10.0.0.9"
    # An address the owner has not named is read straight off the socket.
    assert client_address(FakeRequest("203.0.113.7", "1.2.3.4")) == "203.0.113.7"
    assert client_address(FakeRequest(None)) == "unknown"


def test_both_doors_and_the_storefront_read_the_address_the_same_way():
    assert orders_api.client_address is client_address
    assert storefront_api.client_address is client_address


def test_a_spoofed_header_no_longer_spreads_failures_across_addresses(shop, monkeypatch, transport):
    monkeypatch.delenv("TRUSTED_PROXY_IPS", raising=False)
    monkeypatch.setenv("COURIER_PIN_MAX_FAILURES", "500")
    monkeypatch.setenv("COURIER_PIN_IP_MAX_FAILURES", "3")
    for i in range(3):
        response = shop.post("/pickup/access/verify",
                             headers={"x-forwarded-for": f"1.2.3.{i}"},
                             json={"order_number": f"UA-260903-B{i:03d}", "pin": "000000"})
        assert response.status_code == 403
    order = place_pickup_order(shop)
    assigned = take_to_bay(shop, order)
    blocked = verify_code(shop, order["order_number"], assigned["customer_pickup"]["code"])
    assert blocked.status_code == 429, blocked.text
    rows = open_exceptions(shop, "CUSTOMER_PIN_IP_LOCKOUT")
    assert len(rows) == 1 and rows[0].reference_id == "testclient"


def test_the_storefront_limiter_counts_the_socket_peer_when_no_proxy_is_named(shop, monkeypatch):
    monkeypatch.delenv("TRUSTED_PROXY_IPS", raising=False)
    codes = [shop.post("/v1/storefront/orders/UA-260903-NOPE/cancel",
                       params={"email": BUYER},
                       headers={"x-forwarded-for": f"9.9.9.{i}"}).status_code
             for i in range(11)]
    assert codes[:10] == [404] * 10 and codes[10] == 429


# ------------------------------------------------- 5. an address needs a street


def test_a_structured_address_with_no_street_does_not_open_the_pickup_gate(shop, monkeypatch):
    monkeypatch.delenv("PICKUP_ADDRESS", raising=False)
    monkeypatch.setenv("SHOP_PICKUP_ADDRESS_JSON", json.dumps({"addressLocality": "Ottawa"}))
    config = shop.get("/v1/storefront/config").json()["pickup"]
    assert config["address"] is None
    assert config["address_configured"] is False and config["enabled"] is False

    variant = _variant(shop)
    refused = shop.post("/v1/storefront/orders", json={
        "idempotency_key": f"pickup-{uuid.uuid4()}", "email": BUYER, "name": "Olena Buyer",
        "fulfillment_method": "PICKUP", "ship_to": None,
        "lines": [{"sku": variant["sku"], "qty": 1}],
    })
    assert refused.status_code == 400 and refused.json()["detail"]["code"] == "fulfillment_method"

    # With a street in it the same setting is a working address again.
    monkeypatch.setenv("SHOP_PICKUP_ADDRESS_JSON", json.dumps({
        "streetAddress": "12 Test Lane", "addressLocality": "Ottawa",
        "addressRegion": "ON", "postalCode": "K1A 0B1",
    }))
    live = shop.get("/v1/storefront/config").json()["pickup"]
    assert live["enabled"] is True
    assert live["address"] == "12 Test Lane, Ottawa, ON, K1A 0B1"


# ------------------------------------------------- 6. the two leftovers


def test_a_quote_for_a_method_the_shop_refuses_is_priced_as_shipping(shop, monkeypatch):
    variant = _variant(shop)
    lines = [{"sku": variant["sku"], "qty": 1}]
    monkeypatch.delenv("PICKUP_ADDRESS", raising=False)
    monkeypatch.delenv("SHOP_PICKUP_ADDRESS_JSON", raising=False)

    pickup = shop.post("/v1/storefront/quote", json={
        "lines": lines, "fulfillment_method": "PICKUP", "ship_to": {"province": "ON"}}).json()
    shipped = shop.post("/v1/storefront/quote", json={
        "lines": lines, "fulfillment_method": "SHIP", "ship_to": {"province": "ON"}}).json()
    assert pickup["shipping_cad"] > 0
    assert pickup["shipping_cad"] == shipped["shipping_cad"]
    assert pickup["total_cad"] == shipped["total_cad"]

    # And the moment pickup is a method the shop actually sells, it costs nothing again.
    monkeypatch.setenv("PICKUP_ADDRESS", ADDRESS)
    offered = shop.post("/v1/storefront/quote", json={
        "lines": lines, "fulfillment_method": "PICKUP", "ship_to": {"province": "ON"}}).json()
    assert offered["shipping_cad"] == 0.0
    assert offered["total_cad"] < shipped["total_cad"]


def test_a_credential_past_its_window_keeps_no_readable_digits(shop, transport):
    order = place_pickup_order(shop)
    assigned = take_to_bay(shop, order)
    code = assigned["customer_pickup"]["code"]
    expire_the_code(shop, assigned["order_id"])

    view = customer_view(shop, order["order_number"]).json()["pickup"]
    assert view["state"] == "expired" and view["code"] is None
    rows = access_rows(shop, assigned["order_id"])
    assert len(rows) == 1 and rows[0].display_code is None
    # The hash stays: the row is still the record of a credential that existed.
    assert rows[0].pin_hash and locker.verify_pin(code, rows[0].pin_hash) is True
