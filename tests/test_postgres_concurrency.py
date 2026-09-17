"""Run with TEST_POSTGRES_URL=postgresql+psycopg://... pytest -q tests/test_postgres_concurrency.py"""
import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.models import InventoryBalance, Variant

URL = os.getenv('TEST_POSTGRES_URL')
pytestmark = pytest.mark.skipif(not URL, reason='TEST_POSTGRES_URL not configured')


def test_two_concurrent_reservations_for_last_unit():
    app = create_app(URL)
    c = TestClient(app)
    c.post('/admin/seed')
    c.post('/v1/receipts', json={"sku":"UA-W-BLACK-M","location_id":"A-LANE-01","qty":1,"reference_id":"PG-CONCURRENCY"})
    order_ids=[]
    for i in range(2):
        r=c.post('/webhooks/order', json={"source":"pg","event_id":f"pg-e-{i}","channel":"SHOPIFY","external_order_id":f"pg-o-{i}","lines":[{"sku":"UA-W-BLACK-M","qty":1,"unit_price_cad":79.99}]})
        order_ids.append(r.json()['order_id'])

    def reserve(oid):
        with TestClient(app) as cc:
            return cc.post(f'/v1/orders/{oid}/reserve').status_code

    with ThreadPoolExecutor(max_workers=2) as ex:
        codes=list(ex.map(reserve, order_ids))
    assert sorted(codes) == [200, 409]
    with app.state.SessionLocal() as db:
        v=db.scalar(select(Variant).where(Variant.sku=='UA-W-BLACK-M'))
        bal=db.scalar(select(InventoryBalance).where(InventoryBalance.variant_id==v.id, InventoryBalance.location_id=='A-LANE-01'))
        assert bal.qty_on_hand == 1 and bal.qty_reserved == 1
