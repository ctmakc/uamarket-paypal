from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..edge_models import EdgeCredential
from ..models import Bay, Device, DeviceEvent, OutboxMessage
from .outbox import enqueue


class CommissioningError(RuntimeError):
    pass


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def commissioning_enabled() -> bool:
    return _truthy(os.getenv("COMMISSIONING_ENABLED"))


def _credential(db: Session, *, device_id: str, site: str) -> EdgeCredential:
    row = db.scalar(select(EdgeCredential).where(
        EdgeCredential.device_id == device_id,
        EdgeCredential.site == site,
    ))
    if not row or not row.enabled:
        raise CommissioningError("edge device is not provisioned/enabled for this site")
    return row


def request_state_refresh(db: Session, *, device_id: str, site: str, bay_id: str) -> OutboxMessage:
    _credential(db, device_id=device_id, site=site)
    bay = db.get(Bay, bay_id)
    if not bay or not bay.enabled:
        raise CommissioningError("locker bay is unknown or disabled")
    nonce = uuid4().hex
    return enqueue(
        db,
        topic=f"edge/{site}/{device_id}/commands",
        event_type="READ_LOCKER_STATE",
        aggregate_type="BAY",
        aggregate_id=bay_id,
        payload={"bay_id": bay_id, "device_id": device_id, "commissioning": True},
        idempotency_key=f"commissioning-state:{site}:{device_id}:{bay_id}:{nonce}",
    )


def request_test_unlock(
    db: Session,
    *,
    device_id: str,
    site: str,
    bay_id: str,
    ttl_seconds: int,
    confirm: str,
) -> OutboxMessage:
    if not commissioning_enabled():
        raise CommissioningError("cloud commissioning mode is not enabled")
    if confirm.strip().upper() != "UNLOCK BAY":
        raise CommissioningError('confirmation must be exactly "UNLOCK BAY"')
    _credential(db, device_id=device_id, site=site)
    device = db.get(Device, device_id)
    now = datetime.now(timezone.utc)
    max_age = max(5, int(os.getenv("COMMISSIONING_DEVICE_MAX_AGE_SECONDS", "15")))
    if not device or not device.last_seen_at:
        raise CommissioningError("edge device is not online")
    last_seen = device.last_seen_at
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    if device.state != "ONLINE" or last_seen < now - timedelta(seconds=max_age):
        raise CommissioningError("edge device heartbeat is stale")
    bay = db.get(Bay, bay_id)
    if not bay or not bay.enabled:
        raise CommissioningError("locker bay is unknown or disabled")
    if not bay.inner_gate_closed:
        raise CommissioningError("projected inner gate is open")
    if not bay.outer_door_closed:
        raise CommissioningError("projected outer door is open")
    if not bay.outer_door_locked:
        raise CommissioningError("projected outer lock is already unlocked")
    nonce = uuid4().hex
    return enqueue(
        db,
        topic=f"edge/{site}/{device_id}/commands",
        event_type="COMMISSIONING_UNLOCK_BAY",
        aggregate_type="BAY",
        aggregate_id=bay_id,
        payload={
            "bay_id": bay_id,
            "device_id": device_id,
            "ttl_seconds": max(1, min(int(ttl_seconds), 10)),
            "commissioning": True,
            "expires_at": (now + timedelta(seconds=15)).isoformat(),
        },
        idempotency_key=f"commissioning-unlock:{site}:{device_id}:{bay_id}:{nonce}",
    )


def commissioning_snapshot(
    db: Session,
    *,
    device_id: str,
    site: str,
    event_limit: int = 100,
    stale_seconds: int = 30,
) -> dict:
    credential = _credential(db, device_id=device_id, site=site)
    device = db.get(Device, device_id)
    events = list(db.scalars(
        select(DeviceEvent)
        .where(DeviceEvent.device_id == device_id)
        .order_by(DeviceEvent.created_at.desc())
        .limit(max(1, min(event_limit, 500)))
    ))
    parsed_events = []
    latest_by_bay: dict[str, tuple[datetime, dict, str]] = {}
    for event in events:
        try:
            payload = json.loads(event.payload_json or "{}")
        except Exception:
            payload = {}
        parsed_events.append({
            "id": event.id,
            "event_type": event.event_type,
            "payload": payload,
            "created_at": event.created_at.isoformat(),
        })
        bay_id = payload.get("bay_id")
        if bay_id and bay_id not in latest_by_bay:
            latest_by_bay[bay_id] = (event.created_at, payload, event.event_type)

    now = datetime.now(timezone.utc)
    if device and device.last_seen_at:
        seen = device.last_seen_at
        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=timezone.utc)
        device_stale = seen < now - timedelta(seconds=max(5, stale_seconds))
    else:
        device_stale = True

    bays = []
    for bay in db.scalars(select(Bay).order_by(Bay.id)):
        latest = latest_by_bay.get(bay.id)
        latest_payload = latest[1] if latest else {}
        faults = []
        if not bay.enabled:
            faults.append("BAY_DISABLED")
        if device_stale:
            faults.append("DEVICE_STALE")
        if not latest:
            faults.append("NO_HARDWARE_SNAPSHOT")
        elif latest[0].replace(tzinfo=latest[0].tzinfo or timezone.utc) < now - timedelta(seconds=max(5, stale_seconds)):
            faults.append("HARDWARE_SNAPSHOT_STALE")
        if not bay.inner_gate_closed:
            faults.append("INNER_GATE_OPEN")
        if not bay.outer_door_closed:
            faults.append("OUTER_DOOR_OPEN")
        if not bay.outer_door_locked:
            faults.append("LOCK_FEEDBACK_UNLOCKED")
        if latest_payload.get("unlock_output_active") is True:
            faults.append("UNLOCK_OUTPUT_ACTIVE")
        if latest and latest[2] == "LOCKER_SENSOR_ERROR":
            faults.append("SENSOR_ERROR")
        safe = not faults
        bays.append({
            "bay_id": bay.id,
            "enabled": bay.enabled,
            "inner_gate_closed": bay.inner_gate_closed,
            "outer_door_closed": bay.outer_door_closed,
            "outer_door_locked": bay.outer_door_locked,
            "unlock_output_active": latest_payload.get("unlock_output_active"),
            "last_hardware_event_at": latest[0].isoformat() if latest else None,
            "last_hardware_event_type": latest[2] if latest else None,
            "safe_to_unlock": safe,
            "faults": faults,
        })

    pending = list(db.scalars(
        select(OutboxMessage)
        .where(
            OutboxMessage.state == "PENDING",
            OutboxMessage.topic.like(f"edge/{site}/{device_id}/%"),
            OutboxMessage.event_type.in_(["READ_LOCKER_STATE", "COMMISSIONING_UNLOCK_BAY"]),
        )
        .order_by(OutboxMessage.created_at.desc())
        .limit(50)
    ))
    return {
        "device": {
            "device_id": device_id,
            "site": site,
            "credential_enabled": credential.enabled,
            "state": device.state if device else "UNKNOWN",
            "last_seen_at": device.last_seen_at.isoformat() if device and device.last_seen_at else None,
            "stale": device_stale,
        },
        "commissioning_enabled": commissioning_enabled(),
        "bays": bays,
        "pending_commands": [{
            "id": row.id,
            "event_type": row.event_type,
            "aggregate_id": row.aggregate_id,
            "created_at": row.created_at.isoformat(),
        } for row in pending],
        "recent_events": parsed_events,
    }
