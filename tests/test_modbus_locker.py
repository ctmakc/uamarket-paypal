import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from edge.daemon import EdgeDaemon
from edge.drivers import ModbusBayMap, ModbusLockerDriver


class Result:
    def __init__(self, bit=True, error=False):
        self.bits = [bit]
        self._error = error

    def isError(self):
        return self._error


class FakeModbusClient:
    def __init__(self, bits=None, unlock_feedback=True, auto_open=True):
        self.bits = bits or {0: True, 1: True, 2: True}
        self.unlock_feedback = unlock_feedback
        self.auto_open = auto_open
        self.writes = []
        self.connected = 0
        self.closed = 0

    async def connect(self):
        self.connected += 1
        return True

    async def read_discrete_inputs(self, address, *, count=1, device_id=1):
        return Result(self.bits[address])

    async def read_coils(self, address, *, count=1, device_id=1):
        active = any(a == address and value for a, value, _ in self.writes[-1:])
        return Result(active)

    async def write_coil(self, address, value, *, device_id=1):
        self.writes.append((address, value, device_id))
        if value:
            if self.unlock_feedback:
                self.bits[2] = False
            if self.auto_open:
                self.bits[1] = False
        return Result(True)

    def close(self):
        self.closed += 1


def driver(fake):
    return ModbusLockerDriver(
        host="plc.local",
        port=502,
        device_id=7,
        pulse_ms=100,
        verify_timeout_ms=50,
        bays={"BAY-CP": ModbusBayMap(inner_gate_di=0, outer_door_di=1, lock_feedback_di=2, unlock_coil=5)},
        client_factory=lambda *args, **kwargs: fake,
    )


def test_modbus_unlock_requires_sensor_confirmed_safe_state_feedback_and_door_open():
    fake = FakeModbusClient()
    d = driver(fake)
    state = asyncio.run(d.read_state("BAY-CP"))
    assert state.unlock_output_active is False
    result = asyncio.run(d.unlock("BAY-CP", 60))
    assert result["outer_door_locked"] is False
    assert result["outer_door_closed"] is False
    assert result["door_opened"] is True
    assert fake.writes == [(5, True, 7), (5, False, 7)]
    assert fake.closed >= 2


def test_modbus_unlock_refuses_open_inner_gate_without_actuation():
    fake = FakeModbusClient(bits={0: False, 1: True, 2: True})
    d = driver(fake)
    with pytest.raises(RuntimeError, match="inner gate open"):
        asyncio.run(d.unlock("BAY-CP", 60))
    assert fake.writes == []


def test_modbus_unlock_refuses_open_outer_door_without_actuation():
    fake = FakeModbusClient(bits={0: True, 1: False, 2: True})
    d = driver(fake)
    with pytest.raises(RuntimeError, match="outer door"):
        asyncio.run(d.unlock("BAY-CP", 60))
    assert fake.writes == []


def test_modbus_unlock_fails_closed_if_lock_feedback_does_not_change():
    fake = FakeModbusClient(unlock_feedback=False)
    d = driver(fake)
    with pytest.raises(RuntimeError, match="unlock feedback"):
        asyncio.run(d.unlock("BAY-CP", 60))
    assert fake.writes == [(5, True, 7), (5, False, 7)]


def test_modbus_unlock_fails_if_door_does_not_pop_open():
    fake = FakeModbusClient(auto_open=False)
    d = driver(fake)
    with pytest.raises(RuntimeError, match="outer door did not open"):
        asyncio.run(d.unlock("BAY-CP", 60))
    assert fake.bits[2] is False
    assert fake.bits[1] is True
    assert fake.writes == [(5, True, 7), (5, False, 7)]


def test_modbus_map_accepts_shared_inner_gate_with_unique_door_lock_and_coils():
    d = ModbusLockerDriver(
        host="plc.local",
        bays={
            "BAY-CP": ModbusBayMap(0, 1, 2, 0),
            "BAY-OTHER": ModbusBayMap(0, 3, 4, 1),
            "BAY-OVERFLOW": ModbusBayMap(0, 5, 6, 2),
        },
        client_factory=lambda *args, **kwargs: FakeModbusClient(),
    )
    assert d.describe_map()["BAY-OVERFLOW"]["unlock_coil"] == 2


def test_modbus_map_rejects_duplicate_unlock_coils():
    with pytest.raises(ValueError, match="duplicate unlock_coil"):
        ModbusLockerDriver(
            host="plc.local",
            bays={
                "A": ModbusBayMap(0, 1, 2, 0),
                "B": ModbusBayMap(0, 3, 4, 0),
            },
            client_factory=lambda *args, **kwargs: FakeModbusClient(),
        )


def test_modbus_map_rejects_sensor_channel_overlap():
    with pytest.raises(ValueError, match="door and lock feedback"):
        ModbusLockerDriver(
            host="plc.local",
            bays={
                "A": ModbusBayMap(0, 1, 2, 0),
                "B": ModbusBayMap(0, 3, 1, 1),
            },
            client_factory=lambda *args, **kwargs: FakeModbusClient(),
        )


def test_modbus_map_rejects_out_of_range_channel():
    with pytest.raises(ValueError, match="range 0..7"):
        ModbusLockerDriver(
            host="plc.local",
            bays={"A": ModbusBayMap(0, 1, 2, 8)},
            client_factory=lambda *args, **kwargs: FakeModbusClient(),
        )


def test_cloud_accepts_full_physical_locker_state_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("ALLOW_INSECURE_DEV", "true")
    monkeypatch.setenv("EDGE_SHARED_TOKEN", "dev-edge-token")
    app = create_app(f"sqlite:///{tmp_path / 'state.db'}", create_schema=True)
    c = TestClient(app)
    assert c.post("/admin/seed").status_code == 200
    r = c.post(
        "/edge/events",
        headers={"x-edge-token": "dev-edge-token"},
        json={
            "device_id": "LOCKER-PLC-01",
            "event_type": "LOCKER_STATE",
            "payload": {
                "bay_id": "BAY-CP",
                "inner_gate_closed": False,
                "outer_door_closed": False,
                "outer_door_locked": True,
            },
        },
    )
    assert r.status_code == 200, r.text
    state = c.post("/v1/bays/BAY-CP/state", json={}).json()
    assert state["inner_gate_closed"] is False
    assert state["outer_door_closed"] is False
    assert state["outer_door_locked"] is True


class FakeWS:
    def __init__(self):
        self.sent = []

    async def send(self, raw):
        self.sent.append(json.loads(raw))


def test_edge_daemon_emits_sensor_snapshot_then_transitions(tmp_path, monkeypatch):
    monkeypatch.setenv("EDGE_STATE_DB", str(tmp_path / "edge.db"))
    monkeypatch.setenv("LOCKER_DRIVER", "simulated")
    d = EdgeDaemon()
    ws = FakeWS()
    asyncio.run(d._emit_sensor_events(ws))
    snapshots = [m for m in ws.sent if m.get("event_type") == "LOCKER_STATE"]
    assert len(snapshots) == 3

    ws.sent.clear()
    d.locker.set_outer_door("BAY-CP", False)
    asyncio.run(d._emit_sensor_events(ws))
    assert any(m.get("event_type") == "OUTER_DOOR_OPENED" and m["payload"]["bay_id"] == "BAY-CP" for m in ws.sent)
