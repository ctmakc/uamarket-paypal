from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import InventoryBalance, InventoryEvent, Variant


class InventoryError(RuntimeError):
    pass


def get_variant_by_sku(db: Session, sku: str) -> Variant:
    v = db.scalar(select(Variant).where(Variant.sku == sku))
    if not v:
        raise InventoryError(f"Unknown SKU: {sku}")
    return v


def get_balance(db: Session, variant_id: str, location_id: str, *, lock: bool = False) -> InventoryBalance:
    stmt = select(InventoryBalance).where(
        InventoryBalance.variant_id == variant_id,
        InventoryBalance.location_id == location_id,
    )
    if lock:
        stmt = stmt.with_for_update()
    bal = db.scalar(stmt)
    if not bal:
        bal = InventoryBalance(variant_id=variant_id, location_id=location_id, qty_on_hand=0, qty_reserved=0)
        db.add(bal)
        db.flush()
    return bal


def receive(db: Session, *, variant_id: str, location_id: str, qty: int, reference_id: str):
    bal = get_balance(db, variant_id, location_id, lock=True)
    bal.qty_on_hand += qty
    db.add(InventoryEvent(
        variant_id=variant_id,
        event_type="RECEIVED",
        qty=qty,
        from_location_id=None,
        to_location_id=location_id,
        reference_type="RECEIPT",
        reference_id=reference_id,
    ))


def reserve(db: Session, *, variant_id: str, location_id: str, qty: int, reference_id: str):
    bal = get_balance(db, variant_id, location_id, lock=True)
    if bal.qty_available < qty:
        raise InventoryError(f"Insufficient available inventory: need {qty}, have {bal.qty_available}")
    bal.qty_reserved += qty
    db.add(InventoryEvent(
        variant_id=variant_id,
        event_type="RESERVED",
        qty=qty,
        from_location_id=location_id,
        to_location_id=location_id,
        reference_type="ORDER_LINE",
        reference_id=reference_id,
    ))


def ship_reserved(db: Session, *, variant_id: str, location_id: str, qty: int, reference_id: str):
    bal = get_balance(db, variant_id, location_id, lock=True)
    if bal.qty_reserved < qty or bal.qty_on_hand < qty:
        raise InventoryError("Inventory projection inconsistent during shipment")
    bal.qty_reserved -= qty
    bal.qty_on_hand -= qty
    db.add(InventoryEvent(
        variant_id=variant_id,
        event_type="SHIPPED",
        qty=-qty,
        from_location_id=location_id,
        to_location_id=None,
        reference_type="ORDER_LINE",
        reference_id=reference_id,
    ))


def release(db: Session, *, variant_id: str, location_id: str, qty: int, reference_id: str):
    """Give back units a hold or reservation was keeping, without moving anything physically."""
    bal = get_balance(db, variant_id, location_id, lock=True)
    if bal.qty_reserved < qty:
        raise InventoryError("Inventory projection inconsistent during release")
    bal.qty_reserved -= qty
    db.add(InventoryEvent(
        variant_id=variant_id,
        event_type="RELEASED",
        qty=qty,
        from_location_id=location_id,
        to_location_id=location_id,
        reference_type="ORDER_LINE",
        reference_id=reference_id,
    ))
