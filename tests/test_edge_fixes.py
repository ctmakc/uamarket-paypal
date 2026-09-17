"""Edge and locker safety fixes.

Each test here pins down one way the garage locker could open with nobody in
front of it, or stay energized after it opened:

  1. a transport failure demoting a COMPLETED journal entry, so the cloud
     redelivers the unlock and the bay opens a second time;
  2. an unlock coil that is never proven de-energized;
  3. one provisioned device completing another device's command or rewriting
     another bay's sensor projection;
  4. a revoked credential whose WebSocket stays open and keeps receiving
     UNLOCK commands.
"""
import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from app.main import create_app
from app.models import Bay, CourierPickup, Device, ExceptionRecord, OutboxMessage
from app.services.outbox import enqueue
from edge.daemon import EdgeDaemon
from edge.drivers import ModbusBayMap, ModbusLockerDriver, SimulatedLockerDriver
from edge.drivers.locker import LockerCoilLatchedError

SITE = "garage-ottawa-01"
DEVICE_A = "LOCKER-PLC-01"
DEVICE_B = "LOCKER-PLC-02"


# --------------------------------------------------------------------- fakes


class FakeWS:
    """Collects frames; optionally dies on the frame a predicate selects."""

    def __init__(self, fail_when=None):
        self.sent = []
        self.fail_when = fail_when

    async def send(self, raw):
        message = json.loads(raw)
        if self.fail_when and self.fail_when(message):
            raise ConnectionResetError("edge uplink closed")
        self.sent.append(message)

    def types(self):
        return [m.get("event_type") or m.get("type") for m in self.sent]


class CountingLockerDriver(SimulatedLockerDriver):
    """Simulated driver that counts asks and actual latch movements separately."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.unlock_calls = 0
        self.unlocks = 0

    async def unlock(self, bay_id: str, ttl_seconds: int) -> dict:
        self.unlock_calls += 1
        result = await super().unlock(bay_id, ttl_seconds)
        self.unlocks += 1
        return result


class Result:
    def __init__(self, bit=True, error=False):
        self.bits = [bit]
        self._error = error

    def isError(self):
        return self._error


class FakeModbusClient:
    """Modbus client whose coil keeps the value the PLC actually accepted."""

    def __init__(
        self,
        bits=None,
        unlock_feedback=True,
        auto_open=True,
        off_write_errors=0,
        off_write_raises=0,
        coil_never_drops=False,
    ):
        self.bits = bits or {0: True, 1: True, 2: True}
        self.unlock_feedback = unlock_feedback
        self.auto_open = auto_open
        self.off_write_errors = off_write_errors
        self.off_write_raises = off_write_raises
        self.coil_never_drops = coil_never_drops
        self.coil = False
        self.writes = []
        self.closed = 0

    async def connect(self):
        return True

    async def read_discrete_inputs(self, address, *, count=1, device_id=1):
        return Result(self.bits[address])

    async def read_coils(self, address, *, count=1, device_id=1):
        return Result(self.coil)

    async def write_coil(self, address, value, *, device_id=1):
        self.writes.append((address, value, device_id))
        if value:
            self.coil = True
            if self.unlock_feedback:
                self.bits[2] = False
            if self.auto_open:
                self.bits[1] = False
            return Result(True)
        if self.off_write_raises > 0:
            self.off_write_raises -= 1
            raise ConnectionResetError("PLC stopped answering")
        if self.off_write_errors > 0:
            self.off_write_errors -= 1
            return Result(error=True)
        if not self.coil_never_drops:
            self.coil = False
        return Result(True)

    def close(self):
        self.closed += 1


def modbus_driver(fake, **kwargs):
    options = {
        "pulse_ms": 100,
        "verify_timeout_ms": 50,
        "release_attempts": 3,
        "release_retry_ms": 0,
    }
    options.update(kwargs)
    return ModbusLockerDriver(
        host="plc.local",
        port=502,
        device_id=7,
        bays={"BAY-CP": ModbusBayMap(inner_gate_di=0, outer_door_di=1, lock_feedback_di=2, unlock_coil=5)},
        client_factory=lambda *args, **kw: fake,
        **options,
    )


def daemon(tmp_path, monkeypatch, name="edge.db"):
    monkeypatch.setenv("EDGE_STATE_DB", str(tmp_path / name))
    monkeypatch.setenv("LOCKER_DRIVER", "simulated")
    return EdgeDaemon()


def unlock_command(command_id="cmd-unlock-1", bay_id="BAY-CP"):
    return {
        "id": command_id,
        "event_type": "UNLOCK_BAY",
        "aggregate_id": bay_id,
        "payload": {"bay_id": bay_id, "ttl_seconds": 60},
    }


# ------------------------------------------- 1. journal survives the transport


def test_transport_failure_after_the_pulse_does_not_demote_the_journal(tmp_path, monkeypatch):
    d = daemon(tmp_path, monkeypatch)
    d.locker = CountingLockerDriver()
    ws = FakeWS(fail_when=lambda m: m.get("type") == "EVENT")
    command = unlock_command()

    with pytest.raises(ConnectionResetError):
        asyncio.run(d._handle(ws, command))

    assert d.locker.unlocks == 1
    assert d.store.get("cmd-unlock-1").state == "COMPLETED"


def test_redelivered_completed_command_is_acked_without_touching_the_latch(tmp_path, monkeypatch):
    d = daemon(tmp_path, monkeypatch)
    d.locker = CountingLockerDriver()
    command = unlock_command()

    with pytest.raises(ConnectionResetError):
        asyncio.run(d._handle(FakeWS(fail_when=lambda m: m.get("type") == "EVENT"), command))

    # The cloud still has the row PENDING and redelivers it after the reconnect.
    reconnected = FakeWS()
    asyncio.run(d._handle(reconnected, command))

    assert d.locker.unlock_calls == 1, "a redelivered command must not reach the latch again"
    assert d.locker.unlocks == 1
    replay = [m for m in reconnected.sent if m.get("type") == "EVENT"]
    ack = [m for m in reconnected.sent if m.get("type") == "ACK"]
    assert replay and replay[0]["event_type"] == "LOCKER_UNLOCKED"
    assert replay[0]["payload"]["replayed"] is True
    assert ack == [{"type": "ACK", "command_id": "cmd-unlock-1", "ok": True, "duplicate": True}]


def test_journal_refuses_to_demote_a_completed_command(tmp_path, monkeypatch):
    d = daemon(tmp_path, monkeypatch)
    d.store.remember("cmd-2", unlock_command("cmd-2"))
    d.store.mark_completed("cmd-2", {"bay_id": "BAY-CP"})

    assert d.store.mark_failed("cmd-2", "socket closed") is False
    stored = d.store.get("cmd-2")
    assert stored.state == "COMPLETED" and stored.error is None


def test_command_interrupted_mid_pulse_is_reported_not_repeated(tmp_path, monkeypatch):
    d = daemon(tmp_path, monkeypatch)
    d.locker = CountingLockerDriver()
    command = unlock_command("cmd-3")
    # The daemon died between the journal entry and the result.
    d.store.remember("cmd-3", command)
    d.store.mark_actuating("cmd-3")

    ws = FakeWS()
    asyncio.run(d._handle(ws, command))

    assert d.locker.unlock_calls == 0
    assert ws.types() == ["EDGE_COMMAND_INDETERMINATE", "ACK"]
    ack = ws.sent[-1]
    assert ack["ok"] is False and ack["details"]["indeterminate"] is True


def test_failed_command_still_retries_on_redelivery(tmp_path, monkeypatch):
    d = daemon(tmp_path, monkeypatch)
    d.locker = CountingLockerDriver()
    d.locker.set_inner_gate("BAY-CP", False)
    command = unlock_command("cmd-4")

    first = FakeWS()
    asyncio.run(d._handle(first, command))
    assert first.sent[-1]["ok"] is False
    assert d.store.get("cmd-4").state == "FAILED"

    d.locker.set_inner_gate("BAY-CP", True)
    second = FakeWS()
    asyncio.run(d._handle(second, command))
    assert (d.locker.unlock_calls, d.locker.unlocks) == (2, 1)
    assert second.sent[-1] == {"type": "ACK", "command_id": "cmd-4", "ok": True}


# ------------------------------------------------- 2. coil de-energize proven


def test_unlock_succeeds_only_when_the_coil_is_read_back_off():
    fake = FakeModbusClient()
    result = asyncio.run(modbus_driver(fake).unlock("BAY-CP", 60))
    assert result["unlock_output_active"] is False
    assert result["unlock_output_verified"] is True
    assert fake.coil is False


def test_rejected_de_energize_write_raises_and_reports_a_coil_fault():
    fake = FakeModbusClient(off_write_errors=99)
    driver = modbus_driver(fake)
    faults = []
    driver.fault_handler = lambda event_type, payload: faults.append((event_type, payload))

    with pytest.raises(LockerCoilLatchedError):
        asyncio.run(driver.unlock("BAY-CP", 60))

    assert fake.coil is True, "the fake PLC kept the latch energized"
    assert [w for w in fake.writes if w[1] is False] == [(5, False, 7)] * 3, "every attempt must be retried"
    assert len(faults) == 1
    event_type, payload = faults[0]
    assert event_type == "LOCKER_COIL_LATCHED"
    assert payload["bay_id"] == "BAY-CP" and payload["unlock_coil"] == 5
    assert payload["unlock_output_verified"] is False
    # The PLC answered and refused, so the last coil command it accepted is ON.
    assert payload["unlock_output_active"] is True
    assert payload["attempts"] == 3


def test_coil_that_reads_back_energized_is_a_fault_not_a_successful_unlock():
    fake = FakeModbusClient(coil_never_drops=True)
    driver = modbus_driver(fake)
    faults = []
    driver.fault_handler = lambda event_type, payload: faults.append((event_type, payload))

    with pytest.raises(LockerCoilLatchedError, match="read-back"):
        asyncio.run(driver.unlock("BAY-CP", 60))

    assert faults[0][1]["unlock_output_active"] is True


def test_plc_that_stops_answering_the_off_write_is_a_fault_with_unknown_output():
    fake = FakeModbusClient(off_write_raises=99)
    driver = modbus_driver(fake)
    faults = []
    driver.fault_handler = lambda event_type, payload: faults.append((event_type, payload))

    with pytest.raises(LockerCoilLatchedError):
        asyncio.run(driver.unlock("BAY-CP", 60))

    # Nothing read the coil back, so the driver does not claim to know its state.
    assert faults[0][1]["unlock_output_active"] is None
    assert faults[0][1]["unlock_output_verified"] is False


def test_de_energize_retry_recovers_without_failing_the_unlock():
    fake = FakeModbusClient(off_write_errors=1)
    result = asyncio.run(modbus_driver(fake).unlock("BAY-CP", 60))
    assert result["unlock_output_verified"] is True
    assert fake.coil is False
    assert len([w for w in fake.writes if w[1] is False]) == 2


def test_daemon_forwards_the_coil_fault_and_fails_the_command(tmp_path, monkeypatch):
    d = daemon(tmp_path, monkeypatch)
    fake = FakeModbusClient(off_write_errors=99)
    d.locker = modbus_driver(fake)
    d.locker.fault_handler = d._record_fault

    ws = FakeWS()
    asyncio.run(d._handle(ws, unlock_command("cmd-coil-1")))

    assert ws.types() == ["LOCKER_COIL_LATCHED", "ACK"]
    assert ws.sent[-1]["ok"] is False
    assert d.store.get("cmd-coil-1").state == "FAILED"


# --------------------------------------------------------- cloud test client


def cloud(tmp_path, monkeypatch, name="edge-fixes.db"):
    monkeypatch.setenv("ALLOW_INSECURE_DEV", "false")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    monkeypatch.setenv("OPERATOR_API_KEY", "operator-secret")
    monkeypatch.setenv("EDGE_CREDENTIAL_RECHECK_SECONDS", "0")
    monkeypatch.delenv("EDGE_BAY_OWNERS_JSON", raising=False)
    app = create_app(f"sqlite:///{tmp_path / name}", create_schema=True)
    c = TestClient(app)
    assert c.post("/admin/seed", headers={"x-api-key": "admin-secret"}).status_code == 200
    return app, c


def provision(c, device_id=DEVICE_A, site=SITE):
    r = c.post(
        f"/admin/edge-devices/{device_id}/credentials/rotate",
        params={"site": site},
        headers={"x-api-key": "admin-secret"},
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


def edge_headers(token, device_id=DEVICE_A, site=SITE):
    return {"x-edge-token": token, "x-edge-device-id": device_id, "x-edge-site": site}


def make_pickup(c, bay_id="BAY-CP"):
    now = datetime.now(timezone.utc)
    r = c.post(
        "/v1/pickups",
        headers={"x-api-key": "operator-secret"},
        json={
            "carrier": "Canada Post", "bay_id": bay_id,
            "window_start": (now - timedelta(minutes=1)).isoformat(),
            "window_end": (now + timedelta(hours=1)).isoformat(),
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["pickup_id"]


def route_unlock(app, pickup_id, *, device_id=DEVICE_A, site=SITE, bay_id="BAY-CP", expires_in=120, key="unlock-1"):
    """Enqueue an UNLOCK_BAY exactly the way the courier PIN flow does."""
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    with app.state.SessionLocal() as db:
        msg = enqueue(
            db,
            topic=f"edge/{site}/{device_id}/commands/locker/{bay_id}",
            event_type="UNLOCK_BAY",
            aggregate_type="BAY",
            aggregate_id=bay_id,
            payload={
                "pickup_id": pickup_id, "bay_id": bay_id, "device_id": device_id,
                "action": "UNLOCK", "ttl_seconds": 60, "expires_at": expires_at.isoformat(),
            },
            idempotency_key=key,
        )
        db.commit()
        return msg.id


def exceptions_of(app, kind):
    with app.state.SessionLocal() as db:
        return list(db.scalars(select(ExceptionRecord).where(ExceptionRecord.kind == kind)))


# ------------------------------------------------ 3. events scoped to a device


def test_another_device_cannot_complete_a_command_it_was_never_given(tmp_path, monkeypatch):
    app, c = cloud(tmp_path, monkeypatch)
    provision(c, DEVICE_A)
    token_b = provision(c, DEVICE_B)
    pickup_id = make_pickup(c)
    command_id = route_unlock(app, pickup_id)

    r = c.post(
        "/edge/events",
        headers=edge_headers(token_b, DEVICE_B),
        json={
            "command_id": command_id, "device_id": DEVICE_B,
            "event_type": "LOCKER_UNLOCKED", "payload": {"bay_id": "BAY-CP"},
        },
    )
    assert r.status_code == 200, r.text

    with app.state.SessionLocal() as db:
        assert db.get(OutboxMessage, command_id).state == "PENDING"
        assert db.get(CourierPickup, pickup_id).state != "COURIER_OPEN"
        assert db.get(Bay, "BAY-CP").outer_door_locked is True
    assert [x.reference_id for x in exceptions_of(app, "EDGE_EVENT_SCOPE_VIOLATION")].count(command_id) == 1


def test_the_addressed_device_still_completes_its_own_command(tmp_path, monkeypatch):
    app, c = cloud(tmp_path, monkeypatch)
    token_a = provision(c, DEVICE_A)
    pickup_id = make_pickup(c)
    command_id = route_unlock(app, pickup_id)

    r = c.post(
        "/edge/events",
        headers=edge_headers(token_a, DEVICE_A),
        json={
            "command_id": command_id, "device_id": DEVICE_A,
            "event_type": "LOCKER_UNLOCKED", "payload": {"bay_id": "BAY-CP"},
        },
    )
    assert r.status_code == 200, r.text

    with app.state.SessionLocal() as db:
        assert db.get(OutboxMessage, command_id).state == "DELIVERED"
        assert db.get(CourierPickup, pickup_id).state == "COURIER_OPEN"
        assert db.get(Bay, "BAY-CP").outer_door_locked is False
    assert exceptions_of(app, "EDGE_EVENT_SCOPE_VIOLATION") == []


def test_another_device_cannot_rewrite_a_bay_it_does_not_own(tmp_path, monkeypatch):
    app, c = cloud(tmp_path, monkeypatch)
    provision(c, DEVICE_A)
    token_b = provision(c, DEVICE_B)
    route_unlock(app, make_pickup(c))  # BAY-CP is routed to DEVICE_A

    r = c.post(
        "/edge/events",
        headers=edge_headers(token_b, DEVICE_B),
        json={
            "device_id": DEVICE_B, "event_type": "LOCKER_STATE",
            "payload": {
                "bay_id": "BAY-CP", "inner_gate_closed": False,
                "outer_door_closed": False, "outer_door_locked": False,
            },
        },
    )
    assert r.status_code == 200, r.text

    with app.state.SessionLocal() as db:
        bay = db.get(Bay, "BAY-CP")
        assert (bay.inner_gate_closed, bay.outer_door_closed, bay.outer_door_locked) == (True, True, True)
        # The report is still on file for forensics, attributed to who sent it.
        assert db.scalar(select(Device).where(Device.id == DEVICE_B)) is not None
    assert [x.reference_id for x in exceptions_of(app, "EDGE_EVENT_SCOPE_VIOLATION")] == ["BAY-CP"]


def test_declared_bay_ownership_overrides_command_routing(tmp_path, monkeypatch):
    app, c = cloud(tmp_path, monkeypatch)
    token_a = provision(c, DEVICE_A)
    token_b = provision(c, DEVICE_B)
    monkeypatch.setenv("EDGE_BAY_OWNERS_JSON", json.dumps({f"{SITE}/{DEVICE_B}": ["BAY-CP"]}))

    snapshot = {
        "bay_id": "BAY-CP", "inner_gate_closed": False,
        "outer_door_closed": True, "outer_door_locked": True,
    }
    assert c.post("/edge/events", headers=edge_headers(token_a, DEVICE_A), json={
        "device_id": DEVICE_A, "event_type": "LOCKER_STATE", "payload": snapshot,
    }).status_code == 200
    with app.state.SessionLocal() as db:
        assert db.get(Bay, "BAY-CP").inner_gate_closed is True, "a device without the bay may not write it"

    assert c.post("/edge/events", headers=edge_headers(token_b, DEVICE_B), json={
        "device_id": DEVICE_B, "event_type": "LOCKER_STATE", "payload": snapshot,
    }).status_code == 200
    with app.state.SessionLocal() as db:
        assert db.get(Bay, "BAY-CP").inner_gate_closed is False


def test_replayed_edge_event_completes_the_command_without_writing_stale_sensors(tmp_path, monkeypatch):
    app, c = cloud(tmp_path, monkeypatch)
    token_a = provision(c, DEVICE_A)
    pickup_id = make_pickup(c)
    command_id = route_unlock(app, pickup_id)

    r = c.post(
        "/edge/events",
        headers=edge_headers(token_a, DEVICE_A),
        json={
            "command_id": command_id, "device_id": DEVICE_A, "event_type": "LOCKER_UNLOCKED",
            "payload": {"bay_id": "BAY-CP", "outer_door_locked": False, "replayed": True},
        },
    )
    assert r.status_code == 200, r.text

    with app.state.SessionLocal() as db:
        assert db.get(OutboxMessage, command_id).state == "DELIVERED"
        assert db.get(CourierPickup, pickup_id).state == "COURIER_OPEN"
        # History, not a reading: the live snapshot owns the projection.
        assert db.get(Bay, "BAY-CP").outer_door_locked is True


def test_coil_latched_event_takes_the_bay_out_of_service(tmp_path, monkeypatch):
    app, c = cloud(tmp_path, monkeypatch)
    token_a = provision(c, DEVICE_A)

    r = c.post(
        "/edge/events",
        headers=edge_headers(token_a, DEVICE_A),
        json={
            "device_id": DEVICE_A, "event_type": "LOCKER_COIL_LATCHED",
            "payload": {
                "bay_id": "BAY-CP", "unlock_coil": 5, "attempts": 3,
                "unlock_output_active": True, "unlock_output_verified": False,
                "error": "PLC rejected the unlock coil de-energize write",
            },
        },
    )
    assert r.status_code == 200, r.text

    with app.state.SessionLocal() as db:
        assert db.get(Bay, "BAY-CP").enabled is False
        assert db.get(Device, DEVICE_A).state == "DEGRADED"
    assert len(exceptions_of(app, "LOCKER_COIL_LATCHED")) == 1


# ----------------------------------------------- cloud redelivery has a limit


def test_expired_unlock_is_parked_instead_of_delivered(tmp_path, monkeypatch):
    app, c = cloud(tmp_path, monkeypatch)
    token_a = provision(c, DEVICE_A)
    command_id = route_unlock(app, make_pickup(c), expires_in=-1)

    assert c.get("/edge/commands", headers=edge_headers(token_a)).json()["commands"] == []
    with app.state.SessionLocal() as db:
        assert db.get(OutboxMessage, command_id).state == "EXPIRED"
    assert len(exceptions_of(app, "EDGE_COMMAND_EXPIRED")) == 1


def test_polling_twice_does_not_re_offer_a_command_immediately(tmp_path, monkeypatch):
    app, c = cloud(tmp_path, monkeypatch)
    token_a = provision(c, DEVICE_A)
    route_unlock(app, make_pickup(c))

    assert len(c.get("/edge/commands", headers=edge_headers(token_a)).json()["commands"]) == 1
    # Still inside the retry pause: the device already has this one in hand.
    assert c.get("/edge/commands", headers=edge_headers(token_a)).json()["commands"] == []


def test_undeliverable_command_stops_being_resent(tmp_path, monkeypatch):
    app, c = cloud(tmp_path, monkeypatch)
    monkeypatch.setenv("EDGE_COMMAND_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("EDGE_COMMAND_RETRY_BACKOFF_SECONDS", "0")
    token_a = provision(c, DEVICE_A)
    command_id = route_unlock(app, make_pickup(c))

    for _ in range(2):
        assert len(c.get("/edge/commands", headers=edge_headers(token_a)).json()["commands"]) == 1
    assert c.get("/edge/commands", headers=edge_headers(token_a)).json()["commands"] == []

    with app.state.SessionLocal() as db:
        assert db.get(OutboxMessage, command_id).state == "ABANDONED"
    assert len(exceptions_of(app, "EDGE_COMMAND_ABANDONED")) == 1


def test_websocket_holds_a_command_back_between_attempts(tmp_path, monkeypatch):
    app, c = cloud(tmp_path, monkeypatch)
    token_a = provision(c, DEVICE_A)
    route_unlock(app, make_pickup(c))

    delivered = []
    with c.websocket_connect(
        f"/edge/ws?site={SITE}&device_id={DEVICE_A}", headers={"x-edge-token": token_a}
    ) as ws:
        ws.send_json({"type": "HELLO", "device_id": DEVICE_A, "site": SITE})
        for _ in range(4):
            message = ws.receive_json()
            if message.get("type") == "COMMAND":
                delivered.append(message["command"]["id"])
    assert len(delivered) == 1, "the loop must not re-push the same unlock every pass"


# ---------------------------------------- 4. revocation ends the live session


def test_revoking_a_credential_closes_the_open_websocket(tmp_path, monkeypatch):
    _, c = cloud(tmp_path, monkeypatch)
    token_a = provision(c, DEVICE_A)

    with pytest.raises(WebSocketDisconnect) as exc:
        with c.websocket_connect(
            f"/edge/ws?site={SITE}&device_id={DEVICE_A}", headers={"x-edge-token": token_a}
        ) as ws:
            ws.send_json({"type": "HELLO", "device_id": DEVICE_A, "site": SITE})
            assert ws.receive_json()["type"] == "PING"
            r = c.post(
                f"/admin/edge-devices/{DEVICE_A}/credentials/revoke",
                params={"site": SITE},
                headers={"x-api-key": "admin-secret"},
            )
            assert r.status_code == 200, r.text
            for _ in range(10):
                ws.receive_json()
    assert exc.value.code == 4401


def test_rotating_a_credential_closes_the_session_holding_the_old_token(tmp_path, monkeypatch):
    _, c = cloud(tmp_path, monkeypatch)
    old = provision(c, DEVICE_A)

    with pytest.raises(WebSocketDisconnect) as exc:
        with c.websocket_connect(
            f"/edge/ws?site={SITE}&device_id={DEVICE_A}", headers={"x-edge-token": old}
        ) as ws:
            ws.send_json({"type": "HELLO", "device_id": DEVICE_A, "site": SITE})
            assert ws.receive_json()["type"] == "PING"
            new = provision(c, DEVICE_A)
            assert new != old
            for _ in range(10):
                ws.receive_json()
    assert exc.value.code == 4401
