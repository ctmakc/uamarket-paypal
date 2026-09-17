import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.models import OutboxMessage, Order


def setup(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'integration.db'}", create_schema=True)
    c = TestClient(app)
    assert c.post('/admin/seed').status_code == 200
    return app, c


def sign(raw: bytes, secret: str) -> str:
    return base64.b64encode(hmac.new(secret.encode(), raw, hashlib.sha256).digest()).decode()


def test_shopify_hmac_and_dedupe(tmp_path, monkeypatch):
    app, c = setup(tmp_path)
    monkeypatch.setenv('SHOPIFY_CLIENT_SECRET', 'test-secret')
    assert c.post('/v1/receipts', json={"sku":"UA-W-BLACK-M","location_id":"A-LANE-01","qty":3,"reference_id":"PO-S"}).status_code == 200
    body = json.dumps({
        "id": 987654321,
        "line_items": [{"sku":"UA-W-BLACK-M","quantity":1,"price":"79.99"}],
    }, separators=(',', ':')).encode()
    headers = {
        'content-type': 'application/json',
        'x-shopify-hmac-sha256': sign(body, 'test-secret'),
        'x-shopify-webhook-id': 'shopify-webhook-001',
        'x-shopify-topic': 'orders/paid',
    }
    r1 = c.post('/webhooks/shopify/orders-paid', content=body, headers=headers)
    r2 = c.post('/webhooks/shopify/orders-paid', content=body, headers=headers)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()['order_id'] == r2.json()['order_id']
    assert r2.json()['duplicate'] is True
    with app.state.SessionLocal() as db:
        assert len(list(db.scalars(select(Order)))) == 1


def test_shopify_bad_hmac_rejected(tmp_path, monkeypatch):
    _, c = setup(tmp_path)
    monkeypatch.setenv('SHOPIFY_CLIENT_SECRET', 'test-secret')
    r = c.post('/webhooks/shopify/orders-paid', content=b'{}', headers={
        'content-type':'application/json',
        'x-shopify-hmac-sha256':'wrong',
        'x-shopify-webhook-id':'x',
    })
    assert r.status_code == 401


def test_transactional_outbox_and_edge_ack(tmp_path, monkeypatch):
    app, c = setup(tmp_path)
    monkeypatch.setenv('EDGE_SHARED_TOKEN', 'edge-secret')
    now = datetime.now(timezone.utc)
    p = c.post('/v1/pickups', json={
        'carrier':'Canada Post','bay_id':'BAY-CP',
        'window_start':(now-timedelta(minutes=1)).isoformat(),
        'window_end':(now+timedelta(hours=1)).isoformat(),
    }).json()
    assert c.post('/courier/access/verify', json={'pickup_id':p['pickup_id'],'pin':p['pin']}).status_code == 200
    headers={'x-edge-token':'edge-secret'}
    r = c.get('/edge/commands', headers=headers)
    assert r.status_code == 200
    commands = r.json()['commands']
    assert len(commands) == 1
    cmd = commands[0]
    assert cmd['event_type'] == 'UNLOCK_BAY'
    assert cmd['aggregate_id'] == 'BAY-CP'
    assert c.post(f"/edge/commands/{cmd['id']}/ack", headers=headers, json={'ok':True}).status_code == 200
    assert c.get('/edge/commands', headers=headers).json()['commands'] == []
    with app.state.SessionLocal() as db:
        m = db.get(OutboxMessage, cmd['id'])
        assert m.state == 'DELIVERED' and m.delivered_at is not None


def test_edge_requires_token(tmp_path):
    _, c = setup(tmp_path)
    assert c.get('/edge/commands').status_code == 401


def test_100_duplicate_deliveries_create_one_order(tmp_path):
    app, c = setup(tmp_path)
    payload = {
        "source":"test","event_id":"evt-100x","channel":"SHOPIFY","external_order_id":"ord-100x",
        "lines":[{"sku":"UA-W-BLACK-M","qty":1,"unit_price_cad":79.99}],
    }
    ids = []
    for _ in range(100):
        r = c.post('/webhooks/order', json=payload)
        assert r.status_code == 200
        ids.append(r.json()['order_id'])
    assert len(set(ids)) == 1
    with app.state.SessionLocal() as db:
        assert len(list(db.scalars(select(Order)))) == 1
        accepted = list(db.scalars(select(OutboxMessage).where(OutboxMessage.event_type == 'ORDER_ACCEPTED')))
        assert len(accepted) == 1
