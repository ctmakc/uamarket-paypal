import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import create_app


def _client(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'security.db'}", create_schema=True)
    return TestClient(app)


def _configure(monkeypatch):
    monkeypatch.setenv("ALLOW_INSECURE_DEV", "false")
    monkeypatch.setenv("OPERATOR_API_KEY", "operator-secret")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")


def test_protected_surfaces_fail_closed_when_auth_not_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("ALLOW_INSECURE_DEV", "false")
    monkeypatch.delenv("OPERATOR_API_KEY", raising=False)
    monkeypatch.delenv("ADMIN_API_KEY", raising=False)
    c = _client(tmp_path)
    assert c.get("/health").status_code == 200
    assert c.get("/v1/dashboard").status_code == 503
    assert c.get("/admin/outbox").status_code == 503


def test_operator_and_admin_roles_are_separated(tmp_path, monkeypatch):
    _configure(monkeypatch)
    c = _client(tmp_path)
    assert c.get("/v1/dashboard").status_code == 401
    assert c.get("/v1/dashboard", headers={"x-api-key": "operator-secret"}).status_code == 200
    assert c.get("/admin/outbox", headers={"x-api-key": "operator-secret"}).status_code == 401
    assert c.get("/admin/outbox", headers={"x-api-key": "admin-secret"}).status_code == 200
    assert c.post("/admin/seed", headers={"x-api-key": "operator-secret"}).status_code == 401
    assert c.post("/admin/seed", headers={"x-api-key": "admin-secret"}).status_code == 200


def test_admin_key_can_call_operator_routes(tmp_path, monkeypatch):
    _configure(monkeypatch)
    c = _client(tmp_path)
    assert c.post("/admin/seed", headers={"x-api-key": "admin-secret"}).status_code == 200
    r = c.post("/v1/receipts", headers={"x-api-key": "admin-secret"}, json={"sku":"UA-W-BLACK-M","location_id":"A-LANE-01","qty":1,"reference_id":"SEC-PO"})
    assert r.status_code == 200, r.text


def test_shopify_hmac_remains_public_and_does_not_require_operator_key(tmp_path, monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setenv("SHOPIFY_CLIENT_SECRET", "shopify-secret")
    c = _client(tmp_path)
    assert c.post("/admin/seed", headers={"x-api-key":"admin-secret"}).status_code == 200
    body = json.dumps({"id":12345,"line_items":[{"sku":"UA-W-BLACK-M","quantity":1,"price":"79.99"}]}, separators=(",", ":")).encode()
    signature = base64.b64encode(hmac.new(b"shopify-secret", body, hashlib.sha256).digest()).decode()
    r = c.post("/webhooks/shopify/orders-paid", content=body, headers={"content-type":"application/json","x-shopify-hmac-sha256":signature,"x-shopify-webhook-id":"sec-shopify-1","x-shopify-topic":"orders/paid"})
    assert r.status_code == 200, r.text


def test_courier_pin_surface_remains_public(tmp_path, monkeypatch):
    _configure(monkeypatch)
    c = _client(tmp_path)
    assert c.post("/admin/seed", headers={"x-api-key":"admin-secret"}).status_code == 200
    now = datetime.now(timezone.utc)
    pickup = c.post("/v1/pickups", headers={"x-api-key":"operator-secret"}, json={"carrier":"Canada Post","bay_id":"BAY-CP","window_start":(now-timedelta(minutes=1)).isoformat(),"window_end":(now+timedelta(hours=1)).isoformat()})
    assert pickup.status_code == 200, pickup.text
    p = pickup.json()
    r = c.post("/courier/access/verify", json={"pickup_id":p["pickup_id"],"pin":p["pin"]})
    assert r.status_code == 200, r.text


def test_generic_manual_webhook_requires_operator_auth(tmp_path, monkeypatch):
    _configure(monkeypatch)
    c = _client(tmp_path)
    payload = {"source":"manual","event_id":"sec-manual-1","channel":"SHOPIFY","external_order_id":"sec-order-1","lines":[{"sku":"UA-W-BLACK-M","qty":1,"unit_price_cad":79.99}]}
    assert c.post("/webhooks/order", json=payload).status_code == 401
    assert c.post("/admin/seed", headers={"x-api-key":"admin-secret"}).status_code == 200
    assert c.post("/webhooks/order", headers={"x-api-key":"operator-secret"}, json=payload).status_code == 200
