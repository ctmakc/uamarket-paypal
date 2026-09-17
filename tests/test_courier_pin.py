"""Courier PIN entry: brute-force resistance, PIN storage, and edge-owned bay state.

One app is built for the whole module because building a fresh SQLite schema is by far
the slowest thing here; the fixture below wipes the tables these tests write to, so each
test still starts from a clean bay, an empty exception list and an empty outbox.
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.main import create_app
from app.models import Bay, CourierPickup, ExceptionRecord, LockerAccess, OutboxMessage
from app.services import locker
from app.services.ratelimit import (
    courier_ip_lockout, courier_pin_policy, pickup_pin_lockout, reset_courier_guards,
)

EDGE = {"x-edge-token": "dev-edge-token"}
DEVICE = "LOCKER-PLC-01"
BAY = "BAY-CP"


@pytest.fixture(scope="module")
def stack(tmp_path_factory):
    app = create_app(f"sqlite:///{tmp_path_factory.mktemp('courier') / 'courier.db'}", create_schema=True)
    c = TestClient(app)
    assert c.post("/admin/seed").status_code == 200
    return app, c


@pytest.fixture(autouse=True)
def clean(stack, monkeypatch):
    app, _ = stack
    # The throttles are process-wide singletons; every test starts and ends from zero.
    reset_courier_guards()
    # A low work factor keeps the suite fast. Production default is 200 000 iterations.
    monkeypatch.setenv("LOCKER_PIN_KDF_ITERATIONS", "1000")
    with app.state.SessionLocal() as db:
        for model in (LockerAccess, CourierPickup, ExceptionRecord, OutboxMessage):
            db.execute(delete(model))
        for bay in db.scalars(select(Bay)):
            bay.inner_gate_closed = True
            bay.outer_door_closed = True
            bay.outer_door_locked = True
            bay.weight_g = 0
            bay.enabled = True
        db.commit()
    yield
    reset_courier_guards()


def make_pickup(c, bay_id=BAY, minutes_before=5, hours_after=1):
    now = datetime.now(timezone.utc)
    r = c.post("/v1/pickups", json={
        "carrier": "Canada Post", "bay_id": bay_id,
        "window_start": (now - timedelta(minutes=minutes_before)).isoformat(),
        "window_end": (now + timedelta(hours=hours_after)).isoformat(),
    })
    assert r.status_code == 200, r.text
    return r.json()["pickup_id"], r.json()["pin"]


def wrong_pin(pin, seed=0):
    return f"{(int(pin) + 1 + seed) % 1000000:06d}"


def verify(c, pickup_id, pin):
    return c.post("/courier/access/verify", json={"pickup_id": pickup_id, "pin": pin})


def edge_event(c, event_type, bay_id=BAY, command_id=None):
    r = c.post("/edge/events", headers=EDGE, json={
        "command_id": command_id, "device_id": DEVICE,
        "event_type": event_type, "payload": {"bay_id": bay_id},
    })
    assert r.status_code == 200, r.text


def open_exceptions(app, kind):
    with app.state.SessionLocal() as db:
        return list(db.scalars(select(ExceptionRecord).where(
            ExceptionRecord.kind == kind, ExceptionRecord.state == "OPEN")))


# ------------------------------------------------------------------ happy path


def test_correct_pin_still_opens_the_bay(stack):
    app, c = stack
    pickup_id, pin = make_pickup(c)
    r = verify(c, pickup_id, pin)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True and body["bay_id"] == BAY
    # Cloud still refuses to claim the door moved; that stays an edge report.
    assert body["outer_door_locked"] is True
    assert open_exceptions(app, "COURIER_PIN_LOCKOUT") == []


def test_failed_attempts_below_the_threshold_do_not_block_the_courier(stack, monkeypatch):
    _, c = stack
    monkeypatch.setenv("COURIER_PIN_MAX_FAILURES", "5")
    pickup_id, pin = make_pickup(c)
    for i in range(4):
        assert verify(c, pickup_id, wrong_pin(pin, i)).status_code == 403
    assert verify(c, pickup_id, pin).status_code == 200


# ------------------------------------------------------------------ lockout


def test_wrong_pins_lock_the_pickup_and_the_correct_pin_is_refused(stack, monkeypatch):
    app, c = stack
    monkeypatch.setenv("COURIER_PIN_MAX_FAILURES", "5")
    pickup_id, pin = make_pickup(c)
    for i in range(5):
        assert verify(c, pickup_id, wrong_pin(pin, i)).status_code == 403
    locked = verify(c, pickup_id, pin)
    assert locked.status_code == 429, locked.text
    assert int(locked.headers["retry-after"]) > 0
    assert pickup_pin_lockout.is_locked(pickup_id)
    # The lockout is on the record the operator reads, not only in memory.
    rows = open_exceptions(app, "COURIER_PIN_LOCKOUT")
    assert len(rows) == 1
    assert rows[0].reference_type == "PICKUP" and rows[0].reference_id == pickup_id
    details = json.loads(rows[0].details)
    assert details["failed_attempts"] == 5
    assert details["unlock_endpoint"] == f"/v1/pickups/{pickup_id}/access/unlock"
    assert c.get("/v1/dashboard").json()["exceptions"] >= 1
    # One exception per lockout, not one per rejected attempt.
    assert verify(c, pickup_id, pin).status_code == 429
    assert len(open_exceptions(app, "COURIER_PIN_LOCKOUT")) == 1


def test_operator_can_unlock_a_locked_pickup(stack, monkeypatch):
    app, c = stack
    monkeypatch.setenv("COURIER_PIN_MAX_FAILURES", "3")
    pickup_id, pin = make_pickup(c)
    for i in range(3):
        assert verify(c, pickup_id, wrong_pin(pin, i)).status_code == 403
    assert verify(c, pickup_id, pin).status_code == 429
    r = c.post(f"/v1/pickups/{pickup_id}/access/unlock")
    assert r.status_code == 200, r.text
    assert r.json()["unlocked"] is True
    assert r.json()["cleared_client_ips"] == ["testclient"]
    assert open_exceptions(app, "COURIER_PIN_LOCKOUT") == []
    assert verify(c, pickup_id, pin).status_code == 200


def test_unlock_endpoint_is_operator_only_and_404s_on_an_unknown_pickup(stack, monkeypatch):
    _, c = stack
    assert c.post("/v1/pickups/no-such-pickup/access/unlock").status_code == 404
    monkeypatch.setenv("ALLOW_INSECURE_DEV", "false")
    monkeypatch.setenv("OPERATOR_API_KEY", "operator-secret")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    assert c.post("/v1/pickups/no-such-pickup/access/unlock").status_code == 401
    assert c.post("/v1/pickups/no-such-pickup/access/unlock", headers={"x-api-key": "operator-secret"}).status_code == 404


def test_address_lockout_stops_guessing_across_pickups(stack, monkeypatch):
    app, c = stack
    monkeypatch.setenv("COURIER_PIN_MAX_FAILURES", "50")   # per-pickup guard out of the way
    monkeypatch.setenv("COURIER_PIN_IP_MAX_FAILURES", "4")
    victims = [make_pickup(c) for _ in range(5)]
    for i, (pickup_id, pin) in enumerate(victims[:4]):
        assert verify(c, pickup_id, wrong_pin(pin, i)).status_code == 403
    fresh_id, fresh_pin = victims[4]
    assert verify(c, fresh_id, fresh_pin).status_code == 429
    assert courier_ip_lockout.is_locked("testclient")
    assert len(open_exceptions(app, "COURIER_PIN_IP_LOCKOUT")) == 1


def test_request_flood_is_capped_even_before_the_lockout(stack, monkeypatch):
    _, c = stack
    monkeypatch.setenv("COURIER_PIN_MAX_FAILURES", "500")
    monkeypatch.setenv("COURIER_PIN_IP_MAX_FAILURES", "500")
    monkeypatch.setenv("COURIER_PIN_ATTEMPTS_PER_WINDOW", "6")
    pickup_id, pin = make_pickup(c)
    codes = [verify(c, pickup_id, wrong_pin(pin, i)).status_code for i in range(8)]
    assert codes == [403] * 6 + [429, 429]


def test_guessing_an_unknown_pickup_id_also_locks_out(stack, monkeypatch):
    app, c = stack
    monkeypatch.setenv("COURIER_PIN_MAX_FAILURES", "3")
    for i in range(3):
        assert verify(c, "guessed-id", f"{i:06d}").status_code == 403
    assert verify(c, "guessed-id", "000999").status_code == 429
    assert len(open_exceptions(app, "COURIER_PIN_LOCKOUT")) == 1


def test_default_policy_keeps_a_six_digit_pin_out_of_reach():
    policy = courier_pin_policy()
    assert policy.max_failures <= 10
    assert policy.lockout_seconds >= 300
    # 1 000 000 combinations at 10 tries per 5 minutes still takes years, which is what
    # makes a 6-digit PIN acceptable for a pickup window measured in hours.
    assert 1_000_000 / policy.max_failures * policy.lockout_seconds > 365 * 24 * 3600


# ------------------------------------------------------------------ PIN storage


def test_stored_pin_is_a_salted_slow_hash_not_bare_sha256(stack):
    app, c = stack
    pickup_id, pin = make_pickup(c)
    with app.state.SessionLocal() as db:
        stored = db.scalar(select(LockerAccess).where(LockerAccess.pickup_id == pickup_id)).pin_hash
    assert stored != hashlib.sha256(pin.encode()).hexdigest()
    assert stored.startswith("p2$")
    assert len(stored) <= 64  # locker_access.pin_hash is String(64)
    # Salted: the same PIN hashed twice never lands on the same string.
    assert locker.hash_pin(pin) != locker.hash_pin(pin)
    assert locker.verify_pin(pin, stored) is True
    assert locker.verify_pin(wrong_pin(pin), stored) is False


def test_a_legacy_sha256_row_still_verifies_and_is_upgraded(stack):
    app, c = stack
    pickup_id, pin = make_pickup(c)
    with app.state.SessionLocal() as db:
        access = db.scalar(select(LockerAccess).where(LockerAccess.pickup_id == pickup_id))
        access.pin_hash = hashlib.sha256(pin.encode()).hexdigest()
        db.commit()
    assert verify(c, pickup_id, pin).status_code == 200
    with app.state.SessionLocal() as db:
        access = db.scalar(select(LockerAccess).where(LockerAccess.pickup_id == pickup_id))
        assert access.pin_hash.startswith("p2$")


def test_a_damaged_hash_row_is_rejected_without_crashing(stack):
    app, c = stack
    pickup_id, pin = make_pickup(c)
    with app.state.SessionLocal() as db:
        access = db.scalar(select(LockerAccess).where(LockerAccess.pickup_id == pickup_id))
        access.pin_hash = "p2$not-a-number$@@@$@@@"
        db.commit()
    assert verify(c, pickup_id, pin).status_code == 403


# ------------------------------------------------------------------ edge-owned bay state


def test_operator_cannot_report_hardware_state_as_satisfied(stack):
    _, c = stack
    for field in ("inner_gate_closed", "outer_door_closed"):
        r = c.post(f"/v1/bays/{BAY}/state", json={field: True})
        assert r.status_code == 409, r.text
        assert "edge" in r.json()["detail"]


def test_operator_cannot_flip_a_bay_into_a_handoff_ready_state(stack):
    app, c = stack
    pickup_id, pin = make_pickup(c)
    assert verify(c, pickup_id, pin).status_code == 200
    unlock = next(m for m in c.get("/edge/commands", headers=EDGE).json()["commands"]
                  if m["event_type"] == "UNLOCK_BAY" and m["payload"]["pickup_id"] == pickup_id)
    edge_event(c, "LOCKER_UNLOCKED", command_id=unlock["id"])
    edge_event(c, "OUTER_DOOR_OPENED")
    # Door is open: handoff must fail, and the operator API must not be able to say
    # otherwise by writing the sensor projection.
    assert c.post(f"/v1/bays/{BAY}/handoff").status_code == 409
    assert c.post(f"/v1/bays/{BAY}/state", json={"outer_door_closed": True}).status_code == 409
    assert c.post(f"/v1/bays/{BAY}/handoff").status_code == 409
    edge_event(c, "OUTER_DOOR_CLOSED")
    # Still not re-locked, and outer_door_locked is not writable by the operator at all.
    assert c.post(f"/v1/bays/{BAY}/handoff").status_code == 409
    with app.state.SessionLocal() as db:
        assert db.get(Bay, BAY).outer_door_locked is False
    edge_event(c, "LOCKER_LOCKED")
    assert c.post(f"/v1/bays/{BAY}/handoff").status_code == 200


def test_operator_may_force_a_bay_shut_and_it_is_logged(stack):
    app, c = stack
    r = c.post(f"/v1/bays/{BAY}/state", json={"inner_gate_closed": False})
    assert r.status_code == 200, r.text
    assert r.json()["inner_gate_closed"] is False
    rows = open_exceptions(app, "BAY_MANUAL_HOLD")
    assert len(rows) == 1 and rows[0].reference_id == BAY
    assert json.loads(rows[0].details)["fields"] == ["inner_gate_closed"]
    # The hold blocks the PIN gate, and only the edge can lift it.
    pickup_id, pin = make_pickup(c)
    assert verify(c, pickup_id, pin).status_code == 403
    assert c.post(f"/v1/bays/{BAY}/state", json={"inner_gate_closed": True}).status_code == 409
    edge_event(c, "INNER_GATE_CLOSED")
    assert verify(c, pickup_id, pin).status_code == 200


def test_reading_bay_state_writes_nothing_and_weight_stays_writable(stack):
    app, c = stack
    r = c.post(f"/v1/bays/{BAY}/state", json={})
    assert r.status_code == 200
    assert r.json() == {"id": BAY, "inner_gate_closed": True, "outer_door_closed": True,
                        "outer_door_locked": True, "weight_g": 0}
    r = c.post(f"/v1/bays/{BAY}/state", json={"weight_g": 1200})
    assert r.status_code == 200 and r.json()["weight_g"] == 1200
    assert open_exceptions(app, "BAY_MANUAL_HOLD") == []
