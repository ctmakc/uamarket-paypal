from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import InventoryBalance, InventoryEvent
from .inventory import get_balance


def rebuild_balances(db: Session) -> int:
    """Rebuild the inventory balance projection exclusively from inventory_events."""
    db.execute(delete(InventoryBalance))
    db.flush()
    count = 0
    events = list(db.scalars(select(InventoryEvent).order_by(InventoryEvent.created_at, InventoryEvent.id)))
    for ev in events:
        count += 1
        if ev.event_type == "RECEIVED":
            bal = get_balance(db, ev.variant_id, ev.to_location_id)
            bal.qty_on_hand += ev.qty
        elif ev.event_type == "RESERVED":
            bal = get_balance(db, ev.variant_id, ev.from_location_id)
            bal.qty_reserved += ev.qty
        elif ev.event_type == "RELEASED":
            bal = get_balance(db, ev.variant_id, ev.from_location_id)
            bal.qty_reserved -= ev.qty
        elif ev.event_type == "SHIPPED":
            bal = get_balance(db, ev.variant_id, ev.from_location_id)
            bal.qty_on_hand += ev.qty  # SHIPPED event qty is negative
            bal.qty_reserved += ev.qty  # release the reserved units
        elif ev.event_type == "ADJUSTMENT":
            loc = ev.to_location_id or ev.from_location_id
            bal = get_balance(db, ev.variant_id, loc)
            bal.qty_on_hand += ev.qty
        else:
            raise RuntimeError(f"Unsupported ledger event type during rebuild: {ev.event_type}")
    db.flush()
    return count
