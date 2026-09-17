from __future__ import annotations

import json
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import OutboxMessage


def enqueue(
    db: Session,
    *,
    topic: str,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    payload: dict,
    idempotency_key: str,
) -> OutboxMessage:
    existing = db.scalar(select(OutboxMessage).where(OutboxMessage.idempotency_key == idempotency_key))
    if existing:
        return existing
    msg = OutboxMessage(
        topic=topic,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload_json=json.dumps(payload, separators=(",", ":"), sort_keys=True, default=str),
        idempotency_key=idempotency_key,
    )
    db.add(msg)
    db.flush()
    return msg


def pending(db: Session, *, limit: int = 100, topic_prefix: str | None = None) -> list[OutboxMessage]:
    now = datetime.now(timezone.utc)
    stmt = select(OutboxMessage).where(
        OutboxMessage.state == "PENDING",
        OutboxMessage.available_at <= now,
    ).order_by(OutboxMessage.created_at).limit(limit)
    if topic_prefix:
        stmt = stmt.where(OutboxMessage.topic.like(f"{topic_prefix}%"))
    return list(db.scalars(stmt))


def acknowledge(db: Session, message: OutboxMessage) -> OutboxMessage:
    if message.state != "DELIVERED":
        message.state = "DELIVERED"
        message.attempt_count += 1
        message.delivered_at = datetime.now(timezone.utc)
    return message
