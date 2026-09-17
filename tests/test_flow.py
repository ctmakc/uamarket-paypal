from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.models import InventoryBalance, Order, Variant


def setup_client(tmp_path):
    dbfile = tmp_path / "test.db"
    app = create_app(f"sqlite:///{dbfile}", create_schema=True)
    client = TestClient(app)
    assert client.post("/admin/seed").status_code == 200
    return app, client


def receive(client, sku, loc, qty, ref):
    r = client.post("/v1/receipts", json={"sku": sku, "location_id": loc, "qty": qty, "reference_id": ref})
    assert r.status_code == 200, r.text


def create_order(client, event_id="evt-1", external="ord-1", sku="UA-W-BLACK-M"):
    return client.post("/webhooks/order", json={
        "source": "shopify", "event_id": event_id, "channel": "SHOPIFY", "external_order_id": external,
        "lines": [{"sku": sku, "qty": 1, "unit_price_cad": 79.99}],
    })


def complete_locker_cycle(client, bay_id="BAY-CP"):
    headers = {"x-edge-token": "dev-edge-token"}
    commands = client.get("/edge/commands", headers=headers).json()["commands"]
    unlock = next(c for c in commands if c["event_type"] == "UNLOCK_BAY" and c["aggregate_id"] == bay_id)
    device_id = "LOCKER-PLC-01"
    for event_type, payload in [
        ("LOCKER_UNLOCKED", {"bay_id": bay_id}),
        ("OUTER_DOOR_OPENED", {"bay_id": bay_id}),
        ("OUTER_DOOR_CLOSED", {"bay_id": bay_id}),
        ("LOCKER_LOCKED", {"bay_id": bay_id}),
    ]:
        r = client.post("/edge/events", headers=headers, json={
            "command_id": unlock["id"] if event_type == "LOCKER_UNLOCKED" else None,
            "device_id": device_id, "event_type": event_type, "payload": payload,
        })
        assert r.status_code == 200, r.text


def test_end_to_end(tmp_path):
    app, client = setup_client(tmp_path)
    receive(client, "UA-W-BLACK-M", "A-LANE-01", 3, "PO-001")
    r = create_order(client); assert r.status_code == 200
    oid = r.json()["order_id"]
    r = client.post(f"/v1/orders/{oid}/reserve"); assert r.status_code == 200
    mission = r.json()["missions"][0]
    r = client.post(f"/v1/missions/{mission['id']}/scan-confirm", json={"barcode": "620640001001"}); assert r.status_code == 200
    r = client.post(f"/v1/orders/{oid}/pack"); assert r.status_code == 200
    pid = r.json()["package_id"]
    assert client.post(f"/v1/packages/{pid}/weight", json={"weight_g": 420}).status_code == 200
    assert client.post(f"/v1/packages/{pid}/label-verify", json={"expected_label_code": "CP-TRACK-001", "scanned_label_code": "CP-TRACK-001"}).status_code == 200
    assert client.post(f"/v1/packages/{pid}/assign-bay", json={"bay_id": "BAY-CP"}).status_code == 200
    now = datetime.now(timezone.utc)
    p = client.post("/v1/pickups", json={"carrier": "Canada Post", "bay_id": "BAY-CP", "window_start": (now-timedelta(minutes=5)).isoformat(), "window_end": (now+timedelta(hours=1)).isoformat()})
    assert p.status_code == 200
    pickup_id, pin = p.json()["pickup_id"], p.json()["pin"]
    assert client.post("/courier/access/verify", json={"pickup_id": pickup_id, "pin": pin}).status_code == 200
    assert client.post("/courier/access/verify", json={"pickup_id": pickup_id, "pin": pin}).status_code == 403
    state = client.post("/v1/bays/BAY-CP/state", json={}).json()
    assert state["outer_door_locked"] is True
    assert client.post("/v1/bays/BAY-CP/handoff").status_code == 409
    complete_locker_cycle(client)
    assert client.post("/v1/bays/BAY-CP/handoff").status_code == 200
    with app.state.SessionLocal() as db:
        order = db.get(Order, oid); assert order.state == "HANDOFF_COMPLETE"
        v = db.scalar(select(Variant).where(Variant.sku == "UA-W-BLACK-M"))
        bal = db.scalar(select(InventoryBalance).where(InventoryBalance.variant_id == v.id, InventoryBalance.location_id == "A-LANE-01"))
        assert bal.qty_on_hand == 2 and bal.qty_reserved == 0


def test_duplicate_webhook_is_idempotent(tmp_path):
    _, client = setup_client(tmp_path)
    r1 = create_order(client); r2 = create_order(client)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["order_id"] == r2.json()["order_id"]
    assert r2.json()["duplicate"] is True


def test_last_unit_cannot_be_double_reserved(tmp_path):
    _, client = setup_client(tmp_path)
    receive(client, "UA-W-BLACK-M", "A-LANE-01", 1, "PO-001")
    a = create_order(client, "evt-a", "ord-a").json()["order_id"]
    b = create_order(client, "evt-b", "ord-b").json()["order_id"]
    assert client.post(f"/v1/orders/{a}/reserve").status_code == 200
    assert client.post(f"/v1/orders/{b}/reserve").status_code == 409


def test_wrong_barcode_stops_pick(tmp_path):
    _, client = setup_client(tmp_path)
    receive(client, "UA-W-BLACK-M", "A-LANE-01", 2, "PO-001")
    oid = create_order(client).json()["order_id"]
    mission = client.post(f"/v1/orders/{oid}/reserve").json()["missions"][0]
    r = client.post(f"/v1/missions/{mission['id']}/scan-confirm", json={"barcode": "WRONG"})
    assert r.status_code == 409
    assert client.post(f"/v1/orders/{oid}/pack").status_code == 409


def test_inner_gate_interlock_blocks_courier(tmp_path):
    _, client = setup_client(tmp_path)
    now = datetime.now(timezone.utc)
    p = client.post("/v1/pickups", json={"carrier": "Canada Post", "bay_id": "BAY-CP", "window_start": (now-timedelta(minutes=5)).isoformat(), "window_end": (now+timedelta(hours=1)).isoformat()})
    pickup_id, pin = p.json()["pickup_id"], p.json()["pin"]
    assert client.post("/v1/bays/BAY-CP/state", json={"inner_gate_closed": False}).status_code == 200
    r = client.post("/courier/access/verify", json={"pickup_id": pickup_id, "pin": pin})
    assert r.status_code == 403


def test_label_mismatch_blocks_shipping(tmp_path):
    _, client = setup_client(tmp_path)
    receive(client, "UA-W-BLACK-M", "A-LANE-01", 2, "PO-001")
    oid = create_order(client).json()["order_id"]
    mission = client.post(f"/v1/orders/{oid}/reserve").json()["missions"][0]
    assert client.post(f"/v1/missions/{mission['id']}/scan-confirm", json={"barcode": "620640001001"}).status_code == 200
    pid = client.post(f"/v1/orders/{oid}/pack").json()["package_id"]
    assert client.post(f"/v1/packages/{pid}/weight", json={"weight_g": 410}).status_code == 200
    r = client.post(f"/v1/packages/{pid}/label-verify", json={"expected_label_code": "TRACK-A", "scanned_label_code": "TRACK-B"})
    assert r.status_code == 409
    assert client.post(f"/v1/packages/{pid}/assign-bay", json={"bay_id": "BAY-CP"}).status_code == 409


def test_expired_pin_rejected(tmp_path):
    _, client = setup_client(tmp_path)
    now = datetime.now(timezone.utc)
    p = client.post("/v1/pickups", json={"carrier": "Canada Post", "bay_id": "BAY-CP", "window_start": (now-timedelta(hours=2)).isoformat(), "window_end": (now-timedelta(hours=1)).isoformat()})
    pickup_id, pin = p.json()["pickup_id"], p.json()["pin"]
    assert client.post("/courier/access/verify", json={"pickup_id": pickup_id, "pin": pin}).status_code == 403


def test_same_order_different_event_is_still_idempotent(tmp_path):
    _, client = setup_client(tmp_path)
    r1 = create_order(client, "evt-1", "ord-1")
    r2 = create_order(client, "evt-2", "ord-1")
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["order_id"] == r2.json()["order_id"]
    assert r2.json()["duplicate"] is True


def test_balance_projection_rebuilds_from_ledger(tmp_path):
    app, client = setup_client(tmp_path)
    receive(client, "UA-W-BLACK-M", "A-LANE-01", 5, "PO-001")
    oid = create_order(client).json()["order_id"]
    mission = client.post(f"/v1/orders/{oid}/reserve").json()["missions"][0]
    assert client.post(f"/v1/missions/{mission['id']}/scan-confirm", json={"barcode": "620640001001"}).status_code == 200
    pid = client.post(f"/v1/orders/{oid}/pack").json()["package_id"]
    client.post(f"/v1/packages/{pid}/weight", json={"weight_g": 400})
    client.post(f"/v1/packages/{pid}/label-verify", json={"expected_label_code": "T1", "scanned_label_code": "T1"})
    client.post(f"/v1/packages/{pid}/assign-bay", json={"bay_id": "BAY-CP"})
    now = datetime.now(timezone.utc)
    p = client.post("/v1/pickups", json={"carrier": "Canada Post", "bay_id": "BAY-CP", "window_start": (now-timedelta(minutes=1)).isoformat(), "window_end": (now+timedelta(hours=1)).isoformat()}).json()
    client.post("/courier/access/verify", json={"pickup_id": p["pickup_id"], "pin": p["pin"]})
    complete_locker_cycle(client)
    client.post("/v1/bays/BAY-CP/handoff")
    with app.state.SessionLocal() as db:
        v = db.scalar(select(Variant).where(Variant.sku == "UA-W-BLACK-M"))
        bal = db.scalar(select(InventoryBalance).where(InventoryBalance.variant_id == v.id, InventoryBalance.location_id == "A-LANE-01"))
        bal.qty_on_hand = 999
        bal.qty_reserved = 777
        db.commit()
    r = client.post("/admin/rebuild-balances")
    assert r.status_code == 200
    with app.state.SessionLocal() as db:
        v = db.scalar(select(Variant).where(Variant.sku == "UA-W-BLACK-M"))
        bal = db.scalar(select(InventoryBalance).where(InventoryBalance.variant_id == v.id, InventoryBalance.location_id == "A-LANE-01"))
        assert bal.qty_on_hand == 4
        assert bal.qty_reserved == 0


def test_dashboard_smoke(tmp_path):
    _, client = setup_client(tmp_path)
    receive(client, "UA-W-BLACK-M", "A-LANE-01", 3, "PO-001")
    assert create_order(client).status_code == 200
    r = client.get("/v1/dashboard")
    assert r.status_code == 200
    data = r.json()
    assert data["orders_waiting"] == 1
    assert "exceptions" in data and "parcels_ready" in data
    assert client.get("/").status_code == 200
