import asyncio
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.models import Device, OutboxMessage
from edge.daemon import EdgeDaemon


def setup_client(tmp_path, monkeypatch):
    monkeypatch.setenv("ALLOW_INSECURE_DEV", "false")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    monkeypatch.setenv("OPERATOR_API_KEY", "operator-secret")
    monkeypatch.setenv("COMMISSIONING_ENABLED", "false")
    app = create_app(f"sqlite:///{tmp_path / 'commissioning.db'}", create_schema=True)
    c = TestClient(app)
    assert c.post("/admin/seed", headers={"x-api-key": "admin-secret"}).status_code == 200
    return app, c


def provision(c, device_id="LOCKER-PLC-01", site="garage-ottawa-01"):
    r = c.post(
        f"/admin/edge-devices/{device_id}/credentials/rotate",
        params={"site": site},
        headers={"x-api-key": "admin-secret"},
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


def edge_headers(token, device_id="LOCKER-PLC-01", site="garage-ottawa-01"):
    return {
        "x-edge-token": token,
        "x-edge-device-id": device_id,
        "x-edge-site": site,
    }


def mark_online(c, token, device_id="LOCKER-PLC-01", site="garage-ottawa-01", bay_id="BAY-CP"):
    r = c.post(
        "/edge/events",
        headers=edge_headers(token, device_id, site),
        json={
            "device_id": device_id,
            "event_type": "LOCKER_STATE",
            "payload": {
                "bay_id": bay_id,
                "inner_gate_closed": True,
                "outer_door_closed": True,
                "outer_door_locked": True,
                "unlock_output_active": False,
            },
        },
    )
    assert r.status_code == 200, r.text


def test_commissioning_status_exposes_projected_io_and_recent_hardware_snapshot(tmp_path, monkeypatch):
    _, c = setup_client(tmp_path, monkeypatch)
    token = provision(c)
    mark_online(c, token)
    r = c.get(
        "/admin/commissioning/locker/LOCKER-PLC-01",
        params={"site": "garage-ottawa-01"},
        headers={"x-api-key": "admin-secret"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["device"]["stale"] is False
    bay = next(b for b in data["bays"] if b["bay_id"] == "BAY-CP")
    assert bay["safe_to_unlock"] is True
    assert bay["unlock_output_active"] is False
    assert bay["faults"] == []


def test_refresh_command_is_scoped_to_exact_device_not_only_site(tmp_path, monkeypatch):
    _, c = setup_client(tmp_path, monkeypatch)
    t1 = provision(c, "LOCKER-PLC-01")
    t2 = provision(c, "LOCKER-PLC-02")
    r = c.post(
        "/admin/commissioning/locker/LOCKER-PLC-01/BAY-CP/refresh",
        params={"site": "garage-ottawa-01"},
        headers={"x-api-key": "admin-secret"},
    )
    assert r.status_code == 200, r.text
    first = c.get("/edge/commands", headers=edge_headers(t1, "LOCKER-PLC-01")).json()["commands"]
    second = c.get("/edge/commands", headers=edge_headers(t2, "LOCKER-PLC-02")).json()["commands"]
    assert [x["event_type"] for x in first] == ["READ_LOCKER_STATE"]
    assert second == []


def test_commissioning_unlock_requires_cloud_arm_exact_confirmation_and_fresh_device(tmp_path, monkeypatch):
    app, c = setup_client(tmp_path, monkeypatch)
    token = provision(c)
    mark_online(c, token)
    url = "/admin/commissioning/locker/LOCKER-PLC-01/BAY-CP/test-unlock"
    headers = {"x-api-key": "admin-secret"}

    disabled = c.post(url, headers=headers, json={"site": "garage-ottawa-01", "ttl_seconds": 5, "confirm": "UNLOCK BAY"})
    assert disabled.status_code == 409
    assert "not enabled" in disabled.text

    monkeypatch.setenv("COMMISSIONING_ENABLED", "true")
    wrong = c.post(url, headers=headers, json={"site": "garage-ottawa-01", "ttl_seconds": 5, "confirm": "unlock"})
    assert wrong.status_code == 409

    with app.state.SessionLocal() as db:
        dev = db.get(Device, "LOCKER-PLC-01")
        dev.last_seen_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        db.commit()
    stale = c.post(url, headers=headers, json={"site": "garage-ottawa-01", "ttl_seconds": 5, "confirm": "UNLOCK BAY"})
    assert stale.status_code == 409
    assert "stale" in stale.text

    mark_online(c, token)
    ok = c.post(url, headers=headers, json={"site": "garage-ottawa-01", "ttl_seconds": 5, "confirm": "UNLOCK BAY"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["event_type"] == "COMMISSIONING_UNLOCK_BAY"
    with app.state.SessionLocal() as db:
        msg = db.scalar(select(OutboxMessage).where(OutboxMessage.event_type == "COMMISSIONING_UNLOCK_BAY"))
        assert msg is not None
        assert msg.topic == "edge/garage-ottawa-01/LOCKER-PLC-01/commands"
        assert "expires_at" in msg.payload_json


def test_edge_requires_its_own_commissioning_arm_and_rejects_expired_unlock(tmp_path, monkeypatch):
    monkeypatch.setenv("EDGE_STATE_DB", str(tmp_path / "edge.db"))
    monkeypatch.setenv("LOCKER_DRIVER", "simulated")
    monkeypatch.setenv("EDGE_COMMISSIONING_ENABLED", "false")
    d = EdgeDaemon()
    future = (datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat()
    cmd = {
        "id": "commission-1",
        "event_type": "COMMISSIONING_UNLOCK_BAY",
        "payload": {"bay_id": "BAY-CP", "ttl_seconds": 5, "expires_at": future},
    }
    try:
        asyncio.run(d._execute(cmd))
        assert False, "commissioning unlock must be disabled at edge"
    except RuntimeError as exc:
        assert "not enabled" in str(exc)

    monkeypatch.setenv("EDGE_COMMISSIONING_ENABLED", "true")
    d2 = EdgeDaemon()
    result = asyncio.run(d2._execute(cmd))
    assert result["commissioning"] is True

    expired = {
        "id": "commission-old",
        "event_type": "COMMISSIONING_UNLOCK_BAY",
        "payload": {
            "bay_id": "BAY-OTHER",
            "ttl_seconds": 5,
            "expires_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
        },
    }
    try:
        asyncio.run(d2._execute(expired))
        assert False, "expired command must not actuate"
    except RuntimeError as exc:
        assert "expired" in str(exc)


def test_read_state_command_returns_locker_state_event_type(tmp_path, monkeypatch):
    monkeypatch.setenv("EDGE_STATE_DB", str(tmp_path / "edge.db"))
    monkeypatch.setenv("LOCKER_DRIVER", "simulated")
    d = EdgeDaemon()
    cmd = {"id": "read-1", "event_type": "READ_LOCKER_STATE", "payload": {"bay_id": "BAY-CP"}}
    result = asyncio.run(d._execute(cmd))
    assert result["bay_id"] == "BAY-CP"
    assert result["unlock_output_active"] is False
    assert d._result_event_type(cmd) == "LOCKER_STATE"
