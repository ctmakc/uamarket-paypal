"""Regression tests for four order-pipeline defects.

Each test fails against the code as it stood before this change and passes after it:

1. reserve_order committed the reservations it managed to make before running out of stock, so a
   retry after restock packed a short order the customer had already paid for in full.
2. verify_label trusted the caller for both sides of the comparison, so a mismatch was "fixed" by
   resending the scanned code, and the tracking code EasyPost bound was overwritten.
3. A label buy that timed out left the shipment RATED forever and every retry paid for another label.
4. Nothing set ExceptionRecord.state, so the dashboard's open-exception count only ever grew.
"""
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.models import ExceptionRecord, InventoryBalance, Mission, Order, OrderLine, Package, Reservation, ShipmentRecord, Variant
from app.services.inventory import reserve

ADDRESS = {"street1": "1 Main St", "city": "Ottawa", "state": "ON", "zip": "K1A0A1", "country": "CA"}
BLOUSE = ("UA-W-BLACK-M", "620640001001")


def setup_client(tmp_path, name="fixes.db"):
    app = create_app(f"sqlite:///{tmp_path / name}", create_schema=True)
    client = TestClient(app)
    assert client.post("/admin/seed").status_code == 200
    return app, client


def receive(client, sku, qty, location="A-LANE-01", reference="PO-FIX"):
    r = client.post("/v1/receipts", json={
        "sku": sku, "location_id": location, "qty": qty, "reference_id": reference,
    })
    assert r.status_code == 200, r.text


def create_order(client, lines, event_id="evt-fix", external="ord-fix"):
    r = client.post("/webhooks/order", json={
        "source": "test", "event_id": event_id, "channel": "SHOPIFY", "external_order_id": external,
        "lines": [{"sku": sku, "qty": qty, "unit_price_cad": 79.99} for sku, qty in lines],
    })
    assert r.status_code == 200, r.text
    return r.json()["order_id"]


def balance(app, sku, location="A-LANE-01"):
    with app.state.SessionLocal() as db:
        variant = db.scalar(select(Variant).where(Variant.sku == sku))
        return db.scalar(select(InventoryBalance).where(
            InventoryBalance.variant_id == variant.id, InventoryBalance.location_id == location,
        ))


def packed_package(client, order_id, sku=BLOUSE):
    """Take one single-line order all the way to a weighed package."""
    missions = client.post(f"/v1/orders/{order_id}/reserve").json()["missions"]
    for mission in missions:
        assert client.post(
            f"/v1/missions/{mission['id']}/scan-confirm", json={"barcode": sku[1]},
        ).status_code == 200
    package_id = client.post(f"/v1/orders/{order_id}/pack").json()["package_id"]
    assert client.post(f"/v1/packages/{package_id}/weight", json={"weight_g": 420}).status_code == 200
    return package_id


# --- 1. a failed reservation must leave nothing reserved ------------------------------------
#
# One unit in stock, two paid lines for it. Whichever line the planner looks at first, the second
# one cannot be filled, so the whole order has to fail.

def test_out_of_stock_line_leaves_no_partial_reservation(tmp_path):
    app, client = setup_client(tmp_path)
    receive(client, BLOUSE[0], 1)
    order_id = create_order(client, [(BLOUSE[0], 1), (BLOUSE[0], 1)])

    r = client.post(f"/v1/orders/{order_id}/reserve")
    assert r.status_code == 409, r.text

    with app.state.SessionLocal() as db:
        assert db.get(Order, order_id).state == "OUT_OF_STOCK"
        assert list(db.scalars(select(Mission).where(Mission.order_id == order_id))) == []
        assert list(db.scalars(select(Reservation))) == []
    # The unit stays free for an order that can actually be filled whole.
    assert balance(app, BLOUSE[0]).qty_reserved == 0


def test_the_freed_unit_can_still_be_sold_to_a_fillable_order(tmp_path):
    app, client = setup_client(tmp_path)
    receive(client, BLOUSE[0], 1)
    big = create_order(client, [(BLOUSE[0], 1), (BLOUSE[0], 1)], event_id="evt-big", external="ord-big")
    assert client.post(f"/v1/orders/{big}/reserve").status_code == 409
    small = create_order(client, [(BLOUSE[0], 1)], event_id="evt-small", external="ord-small")
    assert client.post(f"/v1/orders/{small}/reserve").status_code == 200
    assert balance(app, BLOUSE[0]).qty_reserved == 1


def test_retry_after_restock_reserves_the_whole_order(tmp_path):
    app, client = setup_client(tmp_path)
    receive(client, BLOUSE[0], 1)
    order_id = create_order(client, [(BLOUSE[0], 1), (BLOUSE[0], 1)])
    assert client.post(f"/v1/orders/{order_id}/reserve").status_code == 409

    receive(client, BLOUSE[0], 1, reference="PO-RESTOCK")
    r = client.post(f"/v1/orders/{order_id}/reserve")
    assert r.status_code == 200, r.text
    assert len(r.json()["missions"]) == 2

    for mission in r.json()["missions"]:
        assert client.post(
            f"/v1/missions/{mission['id']}/scan-confirm", json={"barcode": BLOUSE[1]},
        ).status_code == 200

    assert client.post(f"/v1/orders/{order_id}/pack").status_code == 200
    with app.state.SessionLocal() as db:
        assert db.get(Order, order_id).state == "PACKING"
        # Both paid-for lines are on the pick plan: nothing ships short.
        assert len(list(db.scalars(select(Mission).where(Mission.order_id == order_id)))) == 2
        assert len(list(db.scalars(select(Reservation)))) == 2
        stockouts = list(db.scalars(select(ExceptionRecord).where(ExceptionRecord.kind == "OUT_OF_STOCK")))
        assert len(stockouts) == 1
        assert stockouts[0].state == "RESOLVED"
    assert balance(app, BLOUSE[0]).qty_reserved == 2


def test_a_half_reserved_order_left_by_older_code_is_completed(tmp_path):
    """Rows the pre-fix code committed must be finished, never mistaken for a full pick plan."""
    app, client = setup_client(tmp_path)
    receive(client, BLOUSE[0], 3)
    order_id = create_order(client, [(BLOUSE[0], 1), (BLOUSE[0], 1)])

    # Reproduce exactly what the old code committed on a stock-out: one line reserved, one not.
    with app.state.SessionLocal() as db:
        order = db.get(Order, order_id)
        line = list(db.scalars(select(OrderLine).where(OrderLine.order_id == order_id)))[0]
        reserve(db, variant_id=line.variant_id, location_id="A-LANE-01", qty=line.qty, reference_id=line.id)
        db.add(Reservation(order_line_id=line.id, variant_id=line.variant_id, location_id="A-LANE-01", qty=line.qty))
        db.add(Mission(order_id=order_id, order_line_id=line.id, variant_id=line.variant_id, location_id="A-LANE-01", qty=line.qty))
        order.state = "OUT_OF_STOCK"
        db.commit()

    r = client.post(f"/v1/orders/{order_id}/reserve")
    assert r.status_code == 200, r.text
    assert len(r.json()["missions"]) == 2
    with app.state.SessionLocal() as db:
        assert len(list(db.scalars(select(Reservation)))) == 2
        assert len(list(db.scalars(select(Mission).where(Mission.order_id == order_id)))) == 2
    assert balance(app, BLOUSE[0]).qty_reserved == 2


def test_a_reserved_line_without_a_mission_gets_one(tmp_path):
    """Stock held for a line nobody was sent to fetch would be left out of the box."""
    app, client = setup_client(tmp_path)
    receive(client, BLOUSE[0], 3)
    order_id = create_order(client, [(BLOUSE[0], 1), (BLOUSE[0], 1)])
    with app.state.SessionLocal() as db:
        line = list(db.scalars(select(OrderLine).where(OrderLine.order_id == order_id)))[0]
        reserve(db, variant_id=line.variant_id, location_id="A-LANE-01", qty=line.qty, reference_id=line.id)
        db.add(Reservation(order_line_id=line.id, variant_id=line.variant_id, location_id="A-LANE-01", qty=line.qty))
        db.commit()

    r = client.post(f"/v1/orders/{order_id}/reserve")
    assert r.status_code == 200, r.text
    assert len(r.json()["missions"]) == 2
    with app.state.SessionLocal() as db:
        missions = list(db.scalars(select(Mission).where(Mission.order_id == order_id)))
        assert {m.order_line_id for m in missions} == {
            l.id for l in db.scalars(select(OrderLine).where(OrderLine.order_id == order_id))
        }
    # The line that was already held is not reserved a second time.
    assert balance(app, BLOUSE[0]).qty_reserved == 2


def test_repeated_stockout_does_not_stack_exceptions(tmp_path):
    app, client = setup_client(tmp_path)
    order_id = create_order(client, [(BLOUSE[0], 1)])
    for _ in range(3):
        assert client.post(f"/v1/orders/{order_id}/reserve").status_code == 409
    with app.state.SessionLocal() as db:
        rows = list(db.scalars(select(ExceptionRecord).where(ExceptionRecord.kind == "OUT_OF_STOCK")))
        assert len(rows) == 1


# --- 2. the carrier's tracking code is the expected label ------------------------------------

class _FakeEasyPost:
    """Minimal EasyPost stand-in. `buy_calls` counts money-moving requests."""

    buy_calls = 0
    fail_first_buy = False
    purchased: dict | None = None

    def __init__(self, api_key):
        assert api_key == "fake-key"

    @classmethod
    def reset(cls, *, fail_first_buy=False):
        cls.buy_calls = 0
        cls.fail_first_buy = fail_first_buy
        cls.purchased = None

    def create_shipment(self, **kwargs):
        return {"id": "shp_1", "rates": [
            {"id": "rate_1", "rate": "11.25", "carrier": "CanadaPost", "service": "ExpeditedParcel", "currency": "CAD"},
        ]}

    def buy_shipment(self, shipment_id, rate_id):
        type(self).buy_calls += 1
        bought = {
            "id": shipment_id, "tracking_code": "CPTRACK1",
            "selected_rate": {"id": rate_id, "rate": "11.25", "carrier": "CanadaPost", "service": "ExpeditedParcel", "currency": "CAD"},
            "postage_label": {"label_url": "https://example/l.png", "label_zpl_url": "https://example/l.zpl"},
        }
        # EasyPost has bound and charged the label; the answer is what gets lost.
        type(self).purchased = bought
        if type(self).fail_first_buy and type(self).buy_calls == 1:
            from app.services.easypost import EasyPostError
            raise EasyPostError("EasyPost transport error: read timeout")
        return bought

    def retrieve_shipment(self, shipment_id):
        if type(self).purchased:
            return type(self).purchased
        return {"id": shipment_id, "tracking_code": None, "postage_label": None}


def buy_label(client, package_id, monkeypatch, *, fail_first_buy=False):
    _FakeEasyPost.reset(fail_first_buy=fail_first_buy)
    monkeypatch.setenv("EASYPOST_API_KEY", "fake-key")
    monkeypatch.setattr("app.api.shipping.EasyPostClient", _FakeEasyPost)
    q = client.post(f"/v1/packages/{package_id}/shipping/easypost/quote", json={
        "to_address": ADDRESS, "from_address": ADDRESS, "length_in": 12, "width_in": 9, "height_in": 2,
    })
    assert q.status_code == 200, q.text
    return client.post(f"/v1/packages/{package_id}/shipping/easypost/buy", json={"rate_id": "rate_1"})


def test_scanned_label_cannot_be_passed_off_as_the_expected_one(tmp_path, monkeypatch):
    app, client = setup_client(tmp_path)
    receive(client, BLOUSE[0], 2)
    order_id = create_order(client, [(BLOUSE[0], 1)])
    package_id = packed_package(client, order_id)
    assert buy_label(client, package_id, monkeypatch).status_code == 200

    # The operator scans the wrong parcel and sends that code as both sides of the comparison.
    r = client.post(f"/v1/packages/{package_id}/label-verify", json={
        "expected_label_code": "SOMEONE-ELSES-PARCEL", "scanned_label_code": "SOMEONE-ELSES-PARCEL",
    })
    assert r.status_code == 409, r.text

    with app.state.SessionLocal() as db:
        package = db.get(Package, package_id)
        assert package.state == "LABEL_FAIL"
        # The code EasyPost bound survives the attempt.
        assert package.expected_label_code == "CPTRACK1"
        assert db.get(Order, order_id).state != "LABEL_VERIFIED"
    # A package that failed its label scan cannot go into a bay.
    assert client.post(f"/v1/packages/{package_id}/assign-bay", json={"bay_id": "BAY-CP"}).status_code == 409


def test_label_verify_passes_on_the_purchased_tracking_code(tmp_path, monkeypatch):
    app, client = setup_client(tmp_path)
    receive(client, BLOUSE[0], 2)
    order_id = create_order(client, [(BLOUSE[0], 1)])
    package_id = packed_package(client, order_id)
    assert buy_label(client, package_id, monkeypatch).status_code == 200

    assert client.post(f"/v1/packages/{package_id}/label-verify", json={
        "expected_label_code": "IGNORED-BY-THE-SERVER", "scanned_label_code": "CPTRACK1",
    }).status_code == 200
    with app.state.SessionLocal() as db:
        package = db.get(Package, package_id)
        assert package.state == "LABEL_VERIFIED"
        assert package.expected_label_code == "CPTRACK1"


def test_label_verify_without_a_bought_label_still_compares_caller_codes(tmp_path):
    """Shops that print their own labels have no ShipmentRecord; that path is unchanged."""
    app, client = setup_client(tmp_path)
    receive(client, BLOUSE[0], 2)
    order_id = create_order(client, [(BLOUSE[0], 1)])
    package_id = packed_package(client, order_id)
    assert client.post(f"/v1/packages/{package_id}/label-verify", json={
        "expected_label_code": "HOUSE-LABEL-7", "scanned_label_code": "HOUSE-LABEL-7",
    }).status_code == 200


# --- 3. a lost buy response must not buy a second label --------------------------------------

def test_timed_out_label_buy_is_recovered_not_repurchased(tmp_path, monkeypatch):
    app, client = setup_client(tmp_path)
    receive(client, BLOUSE[0], 2)
    order_id = create_order(client, [(BLOUSE[0], 1)])
    package_id = packed_package(client, order_id)

    first = buy_label(client, package_id, monkeypatch, fail_first_buy=True)
    assert first.status_code == 502, first.text
    assert _FakeEasyPost.buy_calls == 1
    with app.state.SessionLocal() as db:
        record = db.scalar(select(ShipmentRecord).where(ShipmentRecord.package_id == package_id))
        # The attempt is on record even though its answer was lost.
        assert record.purchase_started_at is not None
        assert record.state != "PURCHASED"

    retry = client.post(f"/v1/packages/{package_id}/shipping/easypost/buy", json={"rate_id": "rate_1"})
    assert retry.status_code == 200, retry.text
    assert retry.json()["tracking_code"] == "CPTRACK1"
    # The label already paid for was recovered; no second label was bought.
    assert _FakeEasyPost.buy_calls == 1
    with app.state.SessionLocal() as db:
        record = db.scalar(select(ShipmentRecord).where(ShipmentRecord.package_id == package_id))
        assert record.state == "PURCHASED"
        assert record.tracking_code == "CPTRACK1"
        assert record.postage_amount == 11.25
        assert db.get(Package, package_id).expected_label_code == "CPTRACK1"

    # And the recovered code is the one the label scan must match.
    assert client.post(f"/v1/packages/{package_id}/label-verify", json={
        "expected_label_code": "CPTRACK1", "scanned_label_code": "CPTRACK1",
    }).status_code == 200


def test_buy_that_never_reached_the_carrier_can_be_retried(tmp_path, monkeypatch):
    """An attempt that bought nothing must not lock the package out of ever getting a label."""
    app, client = setup_client(tmp_path)
    receive(client, BLOUSE[0], 2)
    order_id = create_order(client, [(BLOUSE[0], 1)])
    package_id = packed_package(client, order_id)

    class RefusingEasyPost(_FakeEasyPost):
        """Rejects the first buy outright, so EasyPost never binds a label for it."""

        def buy_shipment(self, shipment_id, rate_id):
            if type(self).buy_calls == 0:
                type(self).buy_calls += 1
                from app.services.easypost import EasyPostError
                raise EasyPostError("EasyPost 422: rate not available")
            return super().buy_shipment(shipment_id, rate_id)

    RefusingEasyPost.reset()
    monkeypatch.setenv("EASYPOST_API_KEY", "fake-key")
    monkeypatch.setattr("app.api.shipping.EasyPostClient", RefusingEasyPost)
    assert client.post(f"/v1/packages/{package_id}/shipping/easypost/quote", json={
        "to_address": ADDRESS, "from_address": ADDRESS, "length_in": 12, "width_in": 9, "height_in": 2,
    }).status_code == 200
    assert client.post(f"/v1/packages/{package_id}/shipping/easypost/buy", json={"rate_id": "rate_1"}).status_code == 502

    retry = client.post(f"/v1/packages/{package_id}/shipping/easypost/buy", json={"rate_id": "rate_1"})
    assert retry.status_code == 200, retry.text
    assert retry.json()["tracking_code"] == "CPTRACK1"
    assert RefusingEasyPost.buy_calls == 2


def test_recovery_reads_the_shipment_back_over_http():
    """The real client has no read-back method yet, so the recovery path must issue the GET itself."""
    import httpx

    from app.api.shipping import _retrieve_shipment
    from app.services.easypost import EasyPostClient

    seen = []

    def handler(request: httpx.Request):
        seen.append((request.method, request.url.path))
        return httpx.Response(200, json={
            "id": "shp_1", "tracking_code": "CPTRACK1",
            "postage_label": {"label_url": "https://example/l.png"},
        })

    client = EasyPostClient("test-key", transport=httpx.MockTransport(handler))
    assert _retrieve_shipment(client, "shp_1")["tracking_code"] == "CPTRACK1"
    assert seen == [("GET", "/v2/shipments/shp_1")]


def test_second_buy_on_a_purchased_shipment_is_free(tmp_path, monkeypatch):
    app, client = setup_client(tmp_path)
    receive(client, BLOUSE[0], 2)
    order_id = create_order(client, [(BLOUSE[0], 1)])
    package_id = packed_package(client, order_id)
    assert buy_label(client, package_id, monkeypatch).status_code == 200
    assert _FakeEasyPost.buy_calls == 1
    again = client.post(f"/v1/packages/{package_id}/shipping/easypost/buy", json={"rate_id": "rate_1"})
    assert again.status_code == 200
    assert again.json()["tracking_code"] == "CPTRACK1"
    assert _FakeEasyPost.buy_calls == 1


# --- 4. exceptions can be closed and the dashboard says so -----------------------------------

def open_one_exception(client):
    """Scan the wrong barcode, which is the cheapest way to raise a real exception."""
    receive(client, BLOUSE[0], 2)
    order_id = create_order(client, [(BLOUSE[0], 1)])
    mission = client.post(f"/v1/orders/{order_id}/reserve").json()["missions"][0]
    assert client.post(
        f"/v1/missions/{mission['id']}/scan-confirm", json={"barcode": "NOT-THE-RIGHT-CODE"},
    ).status_code == 409
    return order_id, mission["id"]


def test_operator_can_resolve_an_exception_and_the_dashboard_agrees(tmp_path):
    app, client = setup_client(tmp_path)
    open_one_exception(client)

    before = client.get("/v1/dashboard").json()
    assert before["exceptions_open"] == 1
    assert before["exceptions_resolved"] == 0
    assert before["exceptions"] == before["exceptions_open"]

    listing = client.get("/v1/exceptions")
    assert listing.status_code == 200, listing.text
    rows = listing.json()["exceptions"]
    assert len(rows) == 1 and rows[0]["kind"] == "WRONG_SKU" and rows[0]["state"] == "OPEN"
    exception_id = rows[0]["id"]

    resolved = client.post(f"/v1/exceptions/{exception_id}/resolve", json={
        "note": "Wrong shelf. Item re-picked from A-LANE-01 and the mission scanned clean.",
        "resolved_by": "warehouse-lead",
    })
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["state"] == "RESOLVED"
    assert resolved.json()["changed"] is True

    after = client.get("/v1/dashboard").json()
    assert after["exceptions_open"] == 0
    assert after["exceptions_resolved"] == 1
    assert after["exceptions_total"] == 1

    with app.state.SessionLocal() as db:
        record = db.get(ExceptionRecord, exception_id)
        assert record.state == "RESOLVED"
        assert record.resolved_by == "warehouse-lead"
        assert record.resolved_at is not None
        assert "re-picked" in record.resolution_note

    assert client.get("/v1/exceptions").json()["exceptions"] == []
    assert len(client.get("/v1/exceptions?state=RESOLVED").json()["exceptions"]) == 1
    assert len(client.get("/v1/exceptions?state=ALL").json()["exceptions"]) == 1
    # The retired dashboard route still answers (it points to /admin).
    assert client.get("/").status_code == 200


def test_resolving_needs_a_note_and_a_real_exception(tmp_path):
    _, client = setup_client(tmp_path)
    _, mission_id = open_one_exception(client)
    exception_id = client.get("/v1/exceptions").json()["exceptions"][0]["id"]
    assert client.post(f"/v1/exceptions/{exception_id}/resolve", json={"note": ""}).status_code == 422
    assert client.post("/v1/exceptions/does-not-exist/resolve", json={"note": "x"}).status_code == 404
    first = client.post(f"/v1/exceptions/{exception_id}/resolve", json={"note": "Re-picked."})
    assert first.json()["changed"] is True
    second = client.post(f"/v1/exceptions/{exception_id}/resolve", json={"note": "Re-picked again."})
    assert second.status_code == 200 and second.json()["changed"] is False
    assert second.json()["resolution_note"] == "Re-picked."


def test_correct_rescan_closes_the_wrong_sku_exception(tmp_path):
    app, client = setup_client(tmp_path)
    _, mission_id = open_one_exception(client)
    assert client.get("/v1/dashboard").json()["exceptions_open"] == 1
    assert client.post(
        f"/v1/missions/{mission_id}/scan-confirm", json={"barcode": BLOUSE[1]},
    ).status_code == 200
    assert client.get("/v1/dashboard").json()["exceptions_open"] == 0
    with app.state.SessionLocal() as db:
        record = db.scalar(select(ExceptionRecord).where(ExceptionRecord.kind == "WRONG_SKU"))
        assert record.state == "RESOLVED" and record.resolved_by == "system"
