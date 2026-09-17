import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import create_app


def setup_client(tmp_path, monkeypatch):
    monkeypatch.setenv("ALLOW_INSECURE_DEV", "false")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    monkeypatch.setenv("OPERATOR_API_KEY", "operator-secret")
    monkeypatch.setenv("EDGE_SHARED_TOKEN", "legacy-shared-secret")
    app = create_app(f"sqlite:///{tmp_path / 'edge-creds.db'}", create_schema=True)
    return app, TestClient(app)


def provision(c, device_id="LOCKER-PLC-01", site="garage-ottawa-01"):
    r = c.post(f"/admin/edge-devices/{device_id}/credentials/rotate", params={"site": site}, headers={"x-api-key": "admin-secret"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def edge_headers(token, device_id="LOCKER-PLC-01", site="garage-ottawa-01"):
    return {"x-edge-token": token, "x-edge-device-id": device_id, "x-edge-site": site}


def test_production_rejects_legacy_shared_token(tmp_path, monkeypatch):
    _, c = setup_client(tmp_path, monkeypatch)
    assert c.get("/edge/commands", headers=edge_headers("legacy-shared-secret")).status_code == 401


def test_per_device_token_authenticates_and_is_listed_without_plaintext(tmp_path, monkeypatch):
    _, c = setup_client(tmp_path, monkeypatch)
    token = provision(c)
    assert c.get("/edge/commands", headers=edge_headers(token)).status_code == 200
    listing = c.get("/admin/edge-devices", headers={"x-api-key": "admin-secret"})
    assert listing.status_code == 200
    row = listing.json()["devices"][0]
    assert row["device_id"] == "LOCKER-PLC-01" and row["site"] == "garage-ottawa-01" and row["enabled"] is True
    assert "token" not in row and "token_hash" not in row
    assert row["last_used_at"] is not None


def test_rotation_invalidates_old_token_immediately(tmp_path, monkeypatch):
    _, c = setup_client(tmp_path, monkeypatch)
    old = provision(c)
    assert c.get("/edge/commands", headers=edge_headers(old)).status_code == 200
    new = provision(c)
    assert old != new
    assert c.get("/edge/commands", headers=edge_headers(old)).status_code == 401
    assert c.get("/edge/commands", headers=edge_headers(new)).status_code == 200


def test_revoke_disables_device_token(tmp_path, monkeypatch):
    _, c = setup_client(tmp_path, monkeypatch)
    token = provision(c)
    r = c.post("/admin/edge-devices/LOCKER-PLC-01/credentials/revoke", params={"site":"garage-ottawa-01"}, headers={"x-api-key":"admin-secret"})
    assert r.status_code == 200
    assert c.get("/edge/commands", headers=edge_headers(token)).status_code == 401


def test_device_token_is_scoped_to_device_and_site(tmp_path, monkeypatch):
    _, c = setup_client(tmp_path, monkeypatch)
    token = provision(c)
    assert c.get("/edge/commands", headers=edge_headers(token, device_id="OTHER-DEVICE")).status_code == 401
    assert c.get("/edge/commands", headers=edge_headers(token, site="other-site")).status_code == 401


def test_websocket_uses_header_token_and_query_token_is_rejected_in_production(tmp_path, monkeypatch):
    _, c = setup_client(tmp_path, monkeypatch)
    token = provision(c)
    with c.websocket_connect("/edge/ws?site=garage-ottawa-01&device_id=LOCKER-PLC-01", headers={"x-edge-token": token}) as ws:
        ws.send_json({"type":"HELLO","device_id":"LOCKER-PLC-01"})
    with pytest.raises(WebSocketDisconnect) as exc:
        with c.websocket_connect(f"/edge/ws?site=garage-ottawa-01&device_id=LOCKER-PLC-01&token={token}"):
            pass
    assert exc.value.code == 4401
