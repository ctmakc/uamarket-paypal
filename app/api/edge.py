from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_db
from ..models import Bay, CourierPickup, Device, DeviceEvent, ExceptionRecord, OutboxMessage
from ..schemas import EdgeAckIn, EdgeEventIn
from ..services.edge_auth import (
    EdgeIdentity,
    authenticate_edge,
    credential_recheck_seconds,
    credential_still_valid,
    insecure_dev_enabled,
)
from ..services.outbox import acknowledge, pending

router = APIRouter()

# Events that say the edge hardware is not in a state we can trust.
DEGRADED_EVENTS = {"LOCKER_SENSOR_ERROR", "LOCKER_COIL_LATCHED", "EDGE_COMMAND_INDETERMINATE"}


def _truthy(value: str | None, default: bool = False) -> bool:
    raw = (value or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def topic_prefix(site: str, device_id: str) -> str:
    return f"edge/{site}/{device_id}/"


def max_delivery_attempts() -> int:
    """How often one command may be pushed to an edge device before it is parked.

    Default 5 (EDGE_COMMAND_MAX_ATTEMPTS). Without a cap the loop re-sends every
    pending row on every pass, so a device that never acknowledges keeps being
    told to open the bay.
    """
    try:
        return max(1, int(os.getenv("EDGE_COMMAND_MAX_ATTEMPTS", "5")))
    except ValueError:
        return 5


def retry_backoff_seconds(attempt: int) -> float:
    """Delay before the same command is offered again. Default 5 s per attempt."""
    try:
        base = max(0.0, float(os.getenv("EDGE_COMMAND_RETRY_BACKOFF_SECONDS", "5")))
    except ValueError:
        base = 5.0
    return min(base * max(1, attempt), 300.0)


def disable_bay_on_coil_fault() -> bool:
    """Take a bay out of service when its unlock coil cannot be proven off.

    Default true (EDGE_DISABLE_BAY_ON_COIL_FAULT). A latch that may still be
    energized is a physical safety incident: the bay stays out of service until
    a person has been to the garage and re-enabled it.
    """
    return _truthy(os.getenv("EDGE_DISABLE_BAY_ON_COIL_FAULT"), default=True)


_owner_cache: tuple[str, dict[str, set[str]] | None] = ("", {})


def _bay_owners() -> dict[str, set[str]] | None:
    """Declared bay ownership, or None when the declaration is unusable.

    EDGE_BAY_OWNERS_JSON maps "<site>/<device_id>" to the bays that device is
    allowed to report, e.g. {"garage-ottawa-01/LOCKER-PLC-01": ["BAY-CP"]}.
    Unset means no declaration; ownership is then derived from the routing the
    cloud itself uses (see device_may_report_bay).
    """
    global _owner_cache
    raw = (os.getenv("EDGE_BAY_OWNERS_JSON") or "").strip()
    if _owner_cache[0] == raw:
        return _owner_cache[1]
    owners: dict[str, set[str]] | None = {}
    if raw:
        try:
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise ValueError("EDGE_BAY_OWNERS_JSON must be an object")
            owners = {
                str(key): {str(bay) for bay in ([value] if isinstance(value, str) else value or [])}
                for key, value in parsed.items()
            }
        except (ValueError, TypeError):
            owners = None
    _owner_cache = (raw, owners)
    return owners


def device_may_report_bay(db: Session, *, site: str, device_id: str, bay_id: str) -> bool:
    """May this device rewrite this bay's sensor projection?

    With a declared ownership map, only the listed owner may. Without one, a bay
    belongs to whichever edge device the cloud routes that bay's commands to; a
    bay nobody has been commanded about yet is reportable by any device at the
    site, because the deployment has not said otherwise.
    """
    owners = _bay_owners()
    if owners is None:
        db.add(ExceptionRecord(
            kind="EDGE_BAY_OWNERS_JSON_INVALID", reference_type="DEVICE", reference_id=device_id,
            details=json.dumps({"site": site, "bay_id": bay_id}),
        ))
    elif owners:
        key = f"{site}/{device_id}"
        if bay_id in owners.get(key, set()):
            return True
        return not any(bay_id in bays for other, bays in owners.items() if other != key)
    routed = db.scalar(
        select(OutboxMessage.topic)
        .where(OutboxMessage.aggregate_type == "BAY", OutboxMessage.aggregate_id == bay_id)
        .order_by(OutboxMessage.created_at.desc())
        .limit(1)
    )
    if not routed:
        return True
    return routed.startswith(topic_prefix(site, device_id))


def _scope_violation(db: Session, *, kind: str, reference_type: str, reference_id: str, details: dict) -> None:
    db.add(ExceptionRecord(
        kind=kind, reference_type=reference_type, reference_id=reference_id, details=json.dumps(details),
    ))


def apply_edge_event(
    db: Session,
    *,
    command_id: str | None,
    device_id: str,
    event_type: str,
    payload: dict,
    site: str = "default",
):
    dev = db.get(Device, device_id)
    if not dev:
        dev = Device(id=device_id, kind="EDGE", state="ONLINE")
        db.add(dev)
    dev.last_seen_at = datetime.now(timezone.utc)
    dev.state = "DEGRADED" if event_type in DEGRADED_EVENTS else "ONLINE"
    db.add(DeviceEvent(device_id=device_id, event_type=event_type, payload_json=json.dumps(payload)))

    # A device may only complete commands addressed to it, at its own site.
    command = db.get(OutboxMessage, command_id) if command_id else None
    if command is not None and not command.topic.startswith(topic_prefix(site, device_id)):
        _scope_violation(
            db, kind="EDGE_EVENT_SCOPE_VIOLATION", reference_type="OUTBOX", reference_id=command.id,
            details={"claimed_by": device_id, "site": site, "event_type": event_type, "topic": command.topic},
        )
        command = None

    # A device may only rewrite the sensor projection of its own bays.
    bay_id = payload.get("bay_id")
    bay = db.get(Bay, bay_id) if bay_id else None
    if bay is not None and not device_may_report_bay(db, site=site, device_id=device_id, bay_id=bay.id):
        _scope_violation(
            db, kind="EDGE_EVENT_SCOPE_VIOLATION", reference_type="BAY", reference_id=bay.id,
            details={"claimed_by": device_id, "site": site, "event_type": event_type},
        )
        bay = None
    if payload.get("replayed"):
        # A replayed journal entry from the edge describes what happened during
        # an earlier connection. It completes the command; the current sensor
        # values arrive in the live snapshots, so it must not write them here.
        bay = None

    if event_type == "LOCKER_STATE":
        if bay:
            if "inner_gate_closed" in payload:
                bay.inner_gate_closed = bool(payload["inner_gate_closed"])
            if "outer_door_closed" in payload:
                bay.outer_door_closed = bool(payload["outer_door_closed"])
            if "outer_door_locked" in payload:
                bay.outer_door_locked = bool(payload["outer_door_locked"])
    elif event_type == "INNER_GATE_OPENED":
        if bay:
            bay.inner_gate_closed = False
    elif event_type == "INNER_GATE_CLOSED":
        if bay:
            bay.inner_gate_closed = True
    elif event_type == "LOCKER_UNLOCKED":
        if bay:
            bay.outer_door_locked = False
        if command is not None:
            try:
                command_payload = json.loads(command.payload_json)
            except Exception:
                command_payload = {}
            pickup_id = command_payload.get("pickup_id")
            pickup = db.get(CourierPickup, pickup_id) if pickup_id else None
            if pickup:
                pickup.state = "COURIER_OPEN"
    elif event_type == "OUTER_DOOR_OPENED":
        if bay:
            bay.outer_door_closed = False
    elif event_type == "OUTER_DOOR_CLOSED":
        if bay:
            bay.outer_door_closed = True
    elif event_type == "LOCKER_LOCKED":
        if bay:
            bay.outer_door_locked = True
    elif event_type == "LOCKER_COIL_LATCHED":
        # The edge could not prove the unlock output went off again. Until a
        # person has checked the panel, the bay is not offered to anyone.
        if bay and disable_bay_on_coil_fault():
            bay.enabled = False
        db.add(ExceptionRecord(
            kind="LOCKER_COIL_LATCHED", reference_type="BAY", reference_id=bay_id or device_id,
            details=json.dumps({"device_id": device_id, "site": site, **payload}),
        ))

    if command is not None and event_type in {"COMMAND_COMPLETED", "LOCKER_UNLOCKED"}:
        acknowledge(db, command)


def _park(db: Session, msg: OutboxMessage, *, state: str, kind: str, details: dict) -> None:
    msg.state = state
    db.add(ExceptionRecord(
        kind=kind, reference_type="OUTBOX", reference_id=msg.id, details=json.dumps(details),
    ))


def _command_expired(msg: OutboxMessage, now: datetime) -> bool:
    try:
        payload = json.loads(msg.payload_json)
    except Exception:
        return False
    raw = payload.get("expires_at")
    if not raw:
        return False
    try:
        expires = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return False
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return now > expires


def deliverable_commands(db: Session, *, site: str, device_id: str, limit: int) -> list[OutboxMessage]:
    """Pending commands this device may still be given.

    Expired unlocks are parked instead of delivered — a command whose window has
    passed must never reach the latch — and so are commands that have used up
    their delivery attempts.
    """
    now = datetime.now(timezone.utc)
    rows = pending(db, limit=limit, topic_prefix=topic_prefix(site, device_id))
    out: list[OutboxMessage] = []
    for msg in rows:
        if _command_expired(msg, now):
            _park(db, msg, state="EXPIRED", kind="EDGE_COMMAND_EXPIRED",
                  details={"device_id": device_id, "site": site, "event_type": msg.event_type})
            continue
        if msg.attempt_count >= max_delivery_attempts():
            _park(db, msg, state="ABANDONED", kind="EDGE_COMMAND_ABANDONED",
                  details={"device_id": device_id, "site": site, "event_type": msg.event_type,
                           "attempt_count": msg.attempt_count})
            continue
        out.append(msg)
    return out


def record_delivery(db: Session, msg: OutboxMessage, *, backoff: bool) -> None:
    """Count one delivery of a command, and optionally hold the next one back."""
    msg.attempt_count += 1
    if backoff:
        msg.available_at = datetime.now(timezone.utc) + timedelta(seconds=retry_backoff_seconds(msg.attempt_count))


def record_nack(db: Session, msg: OutboxMessage, details: dict) -> None:
    db.add(ExceptionRecord(
        kind="EDGE_COMMAND_FAILED", reference_type="OUTBOX", reference_id=msg.id, details=json.dumps(details),
    ))
    if msg.attempt_count >= max_delivery_attempts():
        _park(db, msg, state="ABANDONED", kind="EDGE_COMMAND_ABANDONED",
              details={"event_type": msg.event_type, "attempt_count": msg.attempt_count})
    else:
        msg.available_at = datetime.now(timezone.utc) + timedelta(
            seconds=retry_backoff_seconds(msg.attempt_count + 1)
        )


def _serialize(msg: OutboxMessage) -> dict:
    return {
        "id": msg.id, "topic": msg.topic, "event_type": msg.event_type,
        "aggregate_id": msg.aggregate_id, "payload": json.loads(msg.payload_json),
        "created_at": msg.created_at.isoformat(),
    }


def _authenticate_http(request: Request, db: Session) -> EdgeIdentity:
    identity = authenticate_edge(
        db,
        device_id=request.headers.get("x-edge-device-id"),
        site=request.headers.get("x-edge-site") or "default",
        token=request.headers.get("x-edge-token"),
    )
    if not identity:
        raise HTTPException(401, "Invalid edge device credentials")
    return identity


@router.websocket("/edge/ws")
async def edge_ws(websocket: WebSocket):
    site = websocket.query_params.get("site", "default")
    device_id = websocket.query_params.get("device_id")
    token = websocket.headers.get("x-edge-token")
    if not token and insecure_dev_enabled():
        token = websocket.query_params.get("token")
    with websocket.app.state.SessionLocal() as db:
        identity = authenticate_edge(db, device_id=device_id, site=site, token=token)
        if identity:
            db.commit()
        else:
            db.rollback()
    if not identity:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    prefix = topic_prefix(identity.site, identity.device_id)
    loop = asyncio.get_running_loop()
    next_credential_check = loop.time() + credential_recheck_seconds()
    try:
        while True:
            # A session that authenticated once must not outlive its credential.
            if loop.time() >= next_credential_check:
                with websocket.app.state.SessionLocal() as db:
                    still_valid = credential_still_valid(db, identity=identity, token=token)
                if not still_valid:
                    try:
                        await websocket.close(code=4401)
                    except Exception:
                        pass  # the peer may have gone first; the session ends either way
                    return
                next_credential_check = loop.time() + credential_recheck_seconds()
            with websocket.app.state.SessionLocal() as db:
                rows = deliverable_commands(db, site=identity.site, device_id=identity.device_id, limit=20)
                commands = [_serialize(m) for m in rows]
                for msg in rows:
                    record_delivery(db, msg, backoff=True)
                db.commit()
            for command in commands:
                await websocket.send_json({"type": "COMMAND", "command": command})
            try:
                incoming = await asyncio.wait_for(websocket.receive_json(), timeout=1.0)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "PING"})
                continue
            typ = incoming.get("type")
            if typ in {"HELLO", "PONG"}:
                with websocket.app.state.SessionLocal() as db:
                    dev = db.get(Device, identity.device_id)
                    if not dev:
                        dev = Device(id=identity.device_id, kind="EDGE", state="ONLINE")
                        db.add(dev)
                    dev.last_seen_at = datetime.now(timezone.utc)
                    dev.state = "ONLINE"
                    db.commit()
            elif typ == "EVENT":
                with websocket.app.state.SessionLocal() as db:
                    apply_edge_event(
                        db,
                        command_id=incoming.get("command_id"),
                        device_id=identity.device_id,
                        site=identity.site,
                        event_type=incoming.get("event_type", "UNKNOWN"),
                        payload=incoming.get("payload") or {},
                    )
                    db.commit()
            elif typ == "ACK":
                with websocket.app.state.SessionLocal() as db:
                    msg = db.get(OutboxMessage, incoming.get("command_id"))
                    if msg and msg.topic.startswith(prefix):
                        if incoming.get("ok", True):
                            acknowledge(db, msg)
                        else:
                            record_nack(db, msg, incoming.get("details") or {})
                        db.commit()
                    elif msg is not None:
                        _scope_violation(
                            db, kind="EDGE_ACK_SCOPE_VIOLATION", reference_type="OUTBOX", reference_id=msg.id,
                            details={"claimed_by": identity.device_id, "site": identity.site, "topic": msg.topic},
                        )
                        db.commit()
    except WebSocketDisconnect:
        return


@router.get("/edge/commands")
def edge_commands(limit: int = 50, request: Request = None, db: Session = Depends(get_db)):
    identity = _authenticate_http(request, db)
    rows = deliverable_commands(
        db, site=identity.site, device_id=identity.device_id, limit=min(max(limit, 1), 200)
    )
    commands = [_serialize(m) for m in rows]
    for msg in rows:
        # A poll is a delivery: it counts against the cap and paces the next
        # offer, so a device polling once a second cannot burn five attempts
        # while it is still executing the first one.
        record_delivery(db, msg, backoff=True)
    db.commit()
    return {"commands": commands}


@router.post("/edge/commands/{message_id}/ack")
def edge_ack(message_id: str, inp: EdgeAckIn, request: Request, db: Session = Depends(get_db)):
    identity = _authenticate_http(request, db)
    msg = db.get(OutboxMessage, message_id)
    if not msg or not msg.topic.startswith(topic_prefix(identity.site, identity.device_id)):
        raise HTTPException(404, "Command not found")
    if not inp.ok:
        record_nack(db, msg, inp.details)
    else:
        acknowledge(db, msg)
    db.commit()
    return {"ok": True, "state": msg.state, "attempt_count": msg.attempt_count}


@router.post("/edge/events")
def edge_event(inp: EdgeEventIn, request: Request, db: Session = Depends(get_db)):
    identity = _authenticate_http(request, db)
    apply_edge_event(
        db,
        command_id=inp.command_id,
        device_id=identity.device_id,
        site=identity.site,
        event_type=inp.event_type,
        payload=inp.payload,
    )
    db.commit()
    return {"ok": True}
