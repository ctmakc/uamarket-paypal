from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.models import Bay, CourierPickup, OutboxMessage
from edge.store import EdgeStore
from edge.drivers import SimulatedLockerDriver


def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("EDGE_SHARED_TOKEN", "edge-secret")
    app = create_app(f"sqlite:///{tmp_path / 'edgews.db'}", create_schema=True)
    c = TestClient(app)
    assert c.post("/admin/seed").status_code == 200
    return app, c


def test_cloud_does_not_fake_unlock_and_ws_event_updates_physical_state(tmp_path, monkeypatch):
    app, c = setup(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc)
    p = c.post("/v1/pickups", json={
        "carrier": "Canada Post", "bay_id": "BAY-CP",
        "window_start": (now - timedelta(minutes=1)).isoformat(),
        "window_end": (now + timedelta(hours=1)).isoformat(),
    }).json()
    r = c.post("/courier/access/verify", json={"pickup_id": p["pickup_id"], "pin": p["pin"]})
    assert r.status_code == 200
    assert r.json()["outer_door_locked"] is True

    with c.websocket_connect("/edge/ws?token=edge-secret&site=default&device_id=LOCKER-PLC-01") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "COMMAND"
        cmd = msg["command"]
        assert cmd["event_type"] == "UNLOCK_BAY"
        ws.send_json({
            "type": "EVENT", "command_id": cmd["id"], "device_id": "LOCKER-PLC-01",
            "event_type": "LOCKER_UNLOCKED", "payload": {"bay_id": "BAY-CP"},
        })

    with app.state.SessionLocal() as db:
        bay = db.get(Bay, "BAY-CP")
        pickup = db.get(CourierPickup, p["pickup_id"])
        msg = db.scalar(select(OutboxMessage).where(OutboxMessage.event_type == "UNLOCK_BAY"))
        assert bay.outer_door_locked is False
        assert pickup.state == "COURIER_OPEN"
        assert msg.state == "DELIVERED"


def test_edge_store_prevents_reexecution_after_local_completion(tmp_path):
    store = EdgeStore(str(tmp_path / "edge-state.db"))
    cmd = {"id": "cmd-1", "event_type": "UNLOCK_BAY", "payload": {"bay_id": "BAY-CP"}}
    first = store.remember("cmd-1", cmd)
    assert first.state == "RECEIVED"
    store.mark_completed("cmd-1")
    duplicate = store.remember("cmd-1", cmd)
    assert duplicate.state == "COMPLETED"


def test_simulated_driver_has_its_own_interlock():
    import asyncio
    driver = SimulatedLockerDriver()
    driver.set_inner_gate("BAY-CP", False)
    try:
        asyncio.run(driver.unlock("BAY-CP", 60))
        assert False, "unlock should fail"
    except RuntimeError as exc:
        assert "interlock" in str(exc)
