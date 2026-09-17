import json
import httpx

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.easypost import EasyPostClient


def test_easypost_client_request_shapes():
    seen = []

    def handler(request: httpx.Request):
        seen.append((request.method, request.url.path, json.loads(request.content or b"{}")))
        if request.url.path == "/v2/shipments":
            return httpx.Response(200, json={"id": "shp_1", "rates": [{"id": "rate_1", "rate": "9.50", "carrier": "CanadaPost", "service": "ExpeditedParcel", "currency": "CAD"}]})
        if request.url.path == "/v2/shipments/shp_1/buy":
            return httpx.Response(200, json={
                "id": "shp_1", "tracking_code": "TRACK123",
                "selected_rate": {"id": "rate_1", "rate": "9.50", "carrier": "CanadaPost", "service": "ExpeditedParcel", "currency": "CAD"},
                "postage_label": {"label_url": "https://example/label.png", "label_zpl_url": "https://example/label.zpl"},
            })
        if request.url.path == "/v2/pickups":
            return httpx.Response(200, json={"id": "pickup_1", "status": "unknown", "pickup_rates": [{"carrier": "CanadaPost", "service": "NextDay"}]})
        if request.url.path == "/v2/pickups/pickup_1/buy":
            return httpx.Response(200, json={"id": "pickup_1", "status": "scheduled"})
        return httpx.Response(404)

    client = EasyPostClient("test-key", transport=httpx.MockTransport(handler))
    s = client.create_shipment(
        to_address={"street1": "1 Main", "city": "Ottawa", "state": "ON", "zip": "K1A0A1", "country": "CA"},
        from_address={"street1": "2 Main", "city": "Ottawa", "state": "ON", "zip": "K2K2K2", "country": "CA"},
        parcel={"length": 10, "width": 8, "height": 2, "weight": 16}, reference="pkg-1",
    )
    assert s["id"] == "shp_1"
    assert client.buy_shipment("shp_1", "rate_1")["tracking_code"] == "TRACK123"
    p = client.create_pickup(
        address={"street1": "2 Main", "city": "Ottawa", "state": "ON", "zip": "K2K2K2", "country": "CA"},
        shipment_id="shp_1", carrier_accounts=["ca_1"], min_datetime="2026-09-01T10:00:00-04:00",
        max_datetime="2026-09-01T16:00:00-04:00", instructions="Locker PIN 123456", reference="p-1",
    )
    assert p["id"] == "pickup_1"
    assert client.buy_pickup("pickup_1", "CanadaPost", "NextDay")["status"] == "scheduled"
    assert seen[0][1] == "/v2/shipments"
    assert seen[2][2]["pickup"]["instructions"] == "Locker PIN 123456"


def test_easypost_api_can_rate_buy_and_bind_tracking(tmp_path, monkeypatch):
    app = create_app(f"sqlite:///{tmp_path / 'ship.db'}", create_schema=True)
    c = TestClient(app)
    assert c.post("/admin/seed").status_code == 200
    assert c.post("/v1/receipts", json={"sku":"UA-W-BLACK-M","location_id":"A-LANE-01","qty":2,"reference_id":"PO-1"}).status_code == 200
    oid = c.post("/webhooks/order", json={
        "source":"test","event_id":"e1","channel":"SHOPIFY","external_order_id":"o1",
        "lines":[{"sku":"UA-W-BLACK-M","qty":1,"unit_price_cad":79.99}],
    }).json()["order_id"]
    mission = c.post(f"/v1/orders/{oid}/reserve").json()["missions"][0]
    assert c.post(f"/v1/missions/{mission['id']}/scan-confirm", json={"barcode":"620640001001"}).status_code == 200
    pid = c.post(f"/v1/orders/{oid}/pack").json()["package_id"]
    assert c.post(f"/v1/packages/{pid}/weight", json={"weight_g":420}).status_code == 200

    class FakeEasyPost:
        def __init__(self, api_key):
            assert api_key == "fake-key"
        def create_shipment(self, **kwargs):
            return {"id":"shp_1","rates":[{"id":"rate_1","rate":"11.25","carrier":"CanadaPost","service":"ExpeditedParcel","currency":"CAD"}]}
        def buy_shipment(self, shipment_id, rate_id):
            assert shipment_id == "shp_1" and rate_id == "rate_1"
            return {"tracking_code":"CPTRACK1","selected_rate":{"id":"rate_1","rate":"11.25","carrier":"CanadaPost","service":"ExpeditedParcel","currency":"CAD"},"postage_label":{"label_url":"https://example/l.png","label_zpl_url":"https://example/l.zpl"}}

    monkeypatch.setenv("EASYPOST_API_KEY", "fake-key")
    monkeypatch.setattr("app.api.shipping.EasyPostClient", FakeEasyPost)
    address = {"street1":"1 Main St","city":"Ottawa","state":"ON","zip":"K1A0A1","country":"CA"}
    q = c.post(f"/v1/packages/{pid}/shipping/easypost/quote", json={"to_address":address,"from_address":address,"length_in":12,"width_in":9,"height_in":2})
    assert q.status_code == 200, q.text
    assert q.json()["rates"][0]["id"] == "rate_1"
    b = c.post(f"/v1/packages/{pid}/shipping/easypost/buy", json={"rate_id":"rate_1"})
    assert b.status_code == 200, b.text
    assert b.json()["tracking_code"] == "CPTRACK1"
    v = c.post(f"/v1/packages/{pid}/label-verify", json={"expected_label_code":"CPTRACK1","scanned_label_code":"CPTRACK1"})
    assert v.status_code == 200
