from __future__ import annotations

import hashlib
import json
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    ExceptionRecord, InventoryBalance, Location, Mission, Order, OrderLine, Package,
    Reservation, ShipmentRecord, Variant, WebhookEvent, now_utc,
)
from . import locker
from .inventory import InventoryError, release, reserve, ship_reserved
from .outbox import enqueue


class OrderError(RuntimeError):
    pass


def open_exception(
    db: Session, *, kind: str, reference_type: str, reference_id: str, details: str,
) -> ExceptionRecord:
    """Record an operator-visible exception, one open row per (kind, reference).

    Repeated failures refresh the details of the row that is already open instead of stacking
    duplicates, so the dashboard count stays a count of problems rather than of attempts.
    """
    existing = db.scalar(
        select(ExceptionRecord)
        .where(
            ExceptionRecord.kind == kind,
            ExceptionRecord.reference_type == reference_type,
            ExceptionRecord.reference_id == reference_id,
            ExceptionRecord.state == "OPEN",
        )
        .order_by(ExceptionRecord.created_at)
    )
    if existing:
        existing.details = details
        return existing
    record = ExceptionRecord(
        kind=kind, reference_type=reference_type, reference_id=reference_id, details=details,
    )
    db.add(record)
    return record


def resolve_exception(record: ExceptionRecord, *, note: str, resolved_by: str) -> ExceptionRecord:
    """Close one exception. The note is what the operator (or the system) did about it."""
    record.state = "RESOLVED"
    record.resolution_note = note
    record.resolved_by = resolved_by
    record.resolved_at = now_utc()
    return record


def resolve_open_exceptions(
    db: Session, *, kind: str, reference_type: str, reference_id: str,
    note: str, resolved_by: str = "system",
) -> list[ExceptionRecord]:
    """Close the open exceptions whose condition the pipeline has just cleared by itself."""
    rows = list(db.scalars(select(ExceptionRecord).where(
        ExceptionRecord.kind == kind,
        ExceptionRecord.reference_type == reference_type,
        ExceptionRecord.reference_id == reference_id,
        ExceptionRecord.state == "OPEN",
    )))
    for row in rows:
        resolve_exception(row, note=note, resolved_by=resolved_by)
    return rows


def ingest_order(db: Session, payload: dict) -> tuple[Order, bool]:
    payload_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    prior = db.scalar(select(WebhookEvent).where(
        WebhookEvent.source == payload["source"],
        WebhookEvent.external_event_id == payload["event_id"],
    ))
    if prior:
        order = db.scalar(select(Order).where(
            Order.channel == payload["channel"],
            Order.external_id == payload["external_order_id"],
        ))
        if not order:
            raise OrderError("Webhook recorded but order missing")
        return order, True

    existing = db.scalar(select(Order).where(
        Order.channel == payload["channel"],
        Order.external_id == payload["external_order_id"],
    ))
    if existing:
        db.add(WebhookEvent(source=payload["source"], external_event_id=payload["event_id"], payload_hash=payload_hash))
        return existing, True

    order = Order(channel=payload["channel"], external_id=payload["external_order_id"], state="PAID")
    gross = 0.0
    for line in payload["lines"]:
        variant = db.scalar(select(Variant).where(Variant.sku == line["sku"]))
        if not variant:
            raise OrderError(f"Unknown SKU {line['sku']}")
        order.lines.append(OrderLine(variant_id=variant.id, qty=line["qty"], unit_price_cad=line["unit_price_cad"]))
        gross += line["qty"] * line["unit_price_cad"]
    order.gross_amount_cad = round(gross, 2)
    db.add(order)
    db.add(WebhookEvent(source=payload["source"], external_event_id=payload["event_id"], payload_hash=payload_hash))
    db.flush()
    enqueue(
        db, topic="commerce/orders", event_type="ORDER_ACCEPTED", aggregate_type="ORDER", aggregate_id=order.id,
        payload={"order_id": order.id, "channel": order.channel, "external_id": order.external_id},
        idempotency_key=f"order-accepted:{order.id}",
    )
    return order, False


def _order_reservations(db: Session, order: Order, states: tuple[str, ...]) -> list[Reservation]:
    db.flush()
    return list(db.scalars(
        select(Reservation)
        .join(OrderLine, OrderLine.id == Reservation.order_line_id)
        .where(OrderLine.order_id == order.id, Reservation.state.in_(states))
        .order_by(Reservation.order_line_id, Reservation.location_id)
    ))


def _plan_reservations(db: Session, needs: list[tuple[OrderLine, int]]) -> list[tuple[OrderLine, str, int]]:
    """Choose where every unit comes from before a single unit is reserved.

    A line may be split across sellable locations (the same locations the storefront counts
    as available), fullest location first so a line is split only when it has to be. The
    whole plan is built first so that a line without stock raises before any earlier line
    has been reserved. Balances are locked here (FOR UPDATE where the database supports it)
    and the locks are held for the rest of the transaction. `allocated` carries the units
    this same plan has already promised, which keeps two lines of one order from both
    claiming the last unit.
    """
    from .catalog import SELLABLE_LOCATION_KINDS

    plan: list[tuple[OrderLine, str, int]] = []
    allocated: dict[tuple[str, str], int] = {}
    for line, qty in needs:
        if qty <= 0:
            continue
        balances = list(db.scalars(
            select(InventoryBalance)
            .join(Location, Location.id == InventoryBalance.location_id)
            .where(
                InventoryBalance.variant_id == line.variant_id,
                Location.enabled.is_(True),
                Location.kind.in_(SELLABLE_LOCATION_KINDS),
            )
            .order_by(InventoryBalance.location_id)
            .with_for_update()
        ))
        free = [
            (b.location_id, b.qty_available - allocated.get((b.variant_id, b.location_id), 0))
            for b in balances
        ]
        free = [(loc, n) for loc, n in free if n > 0]
        if sum(n for _, n in free) < qty:
            variant = db.get(Variant, line.variant_id)
            sku = variant.sku if variant else line.variant_id
            raise InventoryError(f"Not enough sellable stock for {qty} x {sku}")
        # Fullest first; ties keep location order, so a plan is deterministic.
        free.sort(key=lambda item: -item[1])
        left = qty
        for location_id, n in free:
            take = min(n, left)
            key = (line.variant_id, location_id)
            allocated[key] = allocated.get(key, 0) + take
            plan.append((line, location_id, take))
            left -= take
            if left == 0:
                break
    return plan


def _apply_plan(db: Session, order: Order, plan: list[tuple[OrderLine, str, int]], *, state: str) -> None:
    """Reserve the planned units in the ledger and record them, merged per (line, location)."""
    existing = {
        (r.order_line_id, r.location_id): r
        for r in _order_reservations(db, order, (state,))
    }
    for line, location_id, qty in plan:
        reserve(db, variant_id=line.variant_id, location_id=location_id, qty=qty, reference_id=line.id)
        row = existing.get((line.id, location_id))
        if row is not None:
            row.qty += qty
        else:
            row = Reservation(
                order_line_id=line.id, variant_id=line.variant_id, location_id=location_id, qty=qty, state=state,
            )
            db.add(row)
            existing[(line.id, location_id)] = row


def hold_stock(db: Session, order: Order, *, until) -> None:
    """Hold every unit of a freshly placed order until `until`, or raise InventoryError.

    Runs in a SAVEPOINT, so a line that cannot be covered leaves nothing held.
    """
    savepoint = db.begin_nested()
    try:
        plan = _plan_reservations(db, [(line, line.qty) for line in order.lines])
        _apply_plan(db, order, plan, state="HOLD")
        db.flush()
        savepoint.commit()
    except InventoryError:
        if savepoint.is_active:
            savepoint.rollback()
        raise
    order.hold_expires_at = until


def release_holds(db: Session, order: Order) -> int:
    """Give back whatever an unpaid order is still holding. Returns the units released."""
    released = 0
    for row in _order_reservations(db, order, ("HOLD",)):
        release(db, variant_id=row.variant_id, location_id=row.location_id, qty=row.qty, reference_id=row.order_line_id)
        row.state = "RELEASED"
        released += row.qty
    order.hold_expires_at = None
    return released


def holds_cover_order(db: Session, order: Order) -> bool:
    held: dict[str, int] = {}
    for row in _order_reservations(db, order, ("HOLD", "ACTIVE")):
        held[row.order_line_id] = held.get(row.order_line_id, 0) + row.qty
    return all(held.get(line.id, 0) >= line.qty for line in order.lines)


def reserve_order(db: Session, order: Order) -> list[Mission]:
    """Reserve every line of the order, or none of what is still missing.

    Units the order already holds from placement become ACTIVE reservations first: the
    order is paid, so they are its own. The top-up for anything still missing runs inside
    a SAVEPOINT. A line without stock rolls the savepoint back, so the transaction the API
    layer commits afterwards carries only the OUT_OF_STOCK state and the exception record,
    never a half-planned pick that a later retry would mistake for a complete one.
    """
    if order.state not in {"PAID", "OUT_OF_STOCK"}:
        return list(db.scalars(select(Mission).where(Mission.order_id == order.id)))

    for held in _order_reservations(db, order, ("HOLD",)):
        held.state = "ACTIVE"
    order.hold_expires_at = None
    db.flush()  # the session does not autoflush, and the reads below must see this

    lines = list(order.lines)
    active = _order_reservations(db, order, ("ACTIVE",))
    reserved: dict[str, int] = {}
    for row in active:
        reserved[row.order_line_id] = reserved.get(row.order_line_id, 0) + row.qty
    needs = [(line, line.qty - reserved.get(line.id, 0)) for line in lines if reserved.get(line.id, 0) < line.qty]
    missions_now = list(db.scalars(select(Mission).where(Mission.order_id == order.id)))
    with_mission = {(m.order_line_id, m.location_id) for m in missions_now}
    if lines and not needs and all((r.order_line_id, r.location_id) in with_mission for r in active):
        # Every line is fully reserved and has its missions: a repeated call, not a new plan.
        order.state = "PICK_PLANNED"
        return missions_now

    savepoint = db.begin_nested()
    try:
        plan = _plan_reservations(db, needs)
        _apply_plan(db, order, plan, state="ACTIVE")
        db.flush()
        # Reserved stock nobody was sent to fetch would be left out of the box, so every
        # reservation gets exactly one mission for its line and location.
        for row in _order_reservations(db, order, ("ACTIVE",)):
            if (row.order_line_id, row.location_id) not in with_mission:
                db.add(Mission(
                    order_id=order.id, order_line_id=row.order_line_id, variant_id=row.variant_id,
                    location_id=row.location_id, qty=row.qty,
                ))
                with_mission.add((row.order_line_id, row.location_id))
        order.state = "PICK_PLANNED"
        db.flush()
        missions = list(db.scalars(select(Mission).where(Mission.order_id == order.id)))
        resolve_open_exceptions(
            db, kind="OUT_OF_STOCK", reference_type="ORDER", reference_id=order.id,
            note="Stock arrived and the whole order reserved on a later attempt.",
        )
        enqueue(
            db, topic="warehouse/missions", event_type="PICK_PLANNED", aggregate_type="ORDER", aggregate_id=order.id,
            payload={"order_id": order.id, "mission_ids": [m.id for m in missions]},
            idempotency_key=f"pick-planned:{order.id}",
        )
        savepoint.commit()
        return missions
    except InventoryError as exc:
        if savepoint.is_active:
            savepoint.rollback()
        order.state = "OUT_OF_STOCK"
        open_exception(
            db, kind="OUT_OF_STOCK", reference_type="ORDER", reference_id=order.id, details=str(exc),
        )
        db.flush()
        raise


def confirm_mission(db: Session, mission: Mission, barcode: str):
    if mission.state == "CONFIRMED":
        return mission
    variant = db.get(Variant, mission.variant_id)
    if not variant or variant.barcode != barcode:
        mission.state = "WRONG_SKU"
        mission.scanned_barcode = barcode
        open_exception(
            db, kind="WRONG_SKU", reference_type="MISSION", reference_id=mission.id,
            details=f"Expected {variant.barcode if variant else '?'} got {barcode}",
        )
        return mission
    mission.state = "CONFIRMED"
    mission.scanned_barcode = barcode
    mission.confirmed_at = now_utc()
    resolve_open_exceptions(
        db, kind="WRONG_SKU", reference_type="MISSION", reference_id=mission.id,
        note="The correct barcode was scanned for this mission afterwards.",
    )
    order = db.get(Order, mission.order_id)
    missions = list(db.scalars(select(Mission).where(Mission.order_id == order.id)))
    if all(m.state == "CONFIRMED" for m in missions):
        order.state = "PICK_VERIFIED"
    else:
        order.state = "PICKING"
    return mission


def create_package(db: Session, order: Order) -> Package:
    existing = db.scalar(select(Package).where(Package.order_id == order.id))
    if existing:
        return existing
    missions = list(db.scalars(select(Mission).where(Mission.order_id == order.id)))
    if not missions or not all(m.state == "CONFIRMED" for m in missions):
        raise OrderError("All pick missions must be confirmed before packing")
    package = Package(order_id=order.id, state="PACKING")
    db.add(package)
    order.state = "PACKING"
    db.flush()
    return package


def bound_tracking_code(db: Session, package: Package) -> str | None:
    """The tracking code the carrier actually bound to this package, if a label was bought."""
    record = db.scalar(select(ShipmentRecord).where(ShipmentRecord.package_id == package.id))
    if record and record.state == "PURCHASED" and record.tracking_code:
        return record.tracking_code
    return None


def verify_label(db: Session, package: Package, expected: str, scanned: str) -> bool:
    """Compare the scanned label against the code the carrier bound to this package.

    Once a label has been bought, the purchased tracking code is the only expected value; the
    `expected` the caller passes is ignored, so a scan mismatch cannot be cleared by resending the
    scanned code as the expectation. Packages shipped without a bought label (no ShipmentRecord)
    keep the caller-supplied expectation, which is all there is to compare against.
    """
    bound = bound_tracking_code(db, package)
    if bound:
        expected = bound
    package.expected_label_code = expected
    package.scanned_label_code = scanned
    order = db.get(Order, package.order_id)
    if expected != scanned:
        package.state = "LABEL_FAIL"
        open_exception(
            db, kind="LABEL_FAIL", reference_type="PACKAGE", reference_id=package.id,
            details=f"Label scan {scanned} does not match the label on this package ({expected}).",
        )
        return False
    package.state = "LABEL_VERIFIED"
    order.state = "LABEL_VERIFIED"
    resolve_open_exceptions(
        db, kind="LABEL_FAIL", reference_type="PACKAGE", reference_id=package.id,
        note="The correct label was scanned for this package afterwards.",
    )
    return True


PICKUP_NOT_CONFIGURED = "PICKUP_NOT_CONFIGURED"


def issue_pickup_code(db: Session, order: Order, bay_id: str):
    """Mint the buyer's own one-time code for the bay their parcel just went into.

    Only a web order the buyer chose to collect gets one. The code is minted here, at the
    moment the parcel is physically in the bay, so the shop never holds a code for a bay
    that holds nothing. Returns the credential, or None when this order earns no code.

    A pickup order that reaches a bay while `PICKUP_ADDRESS` is unset leaves an exception on
    the operator's list instead of a code: the buyer would receive digits and no building.
    """
    if order.channel != "WEB" or (order.fulfillment_method or "") != "PICKUP":
        return None
    if not locker.pickup_address():
        open_exception(
            db, kind=PICKUP_NOT_CONFIGURED, reference_type="ORDER", reference_id=order.id,
            details=(
                f"Order {order.order_number or order.id} was bought for locker pickup and "
                "PICKUP_ADDRESS is empty, so no code and no address can be given to the buyer. "
                "Set PICKUP_ADDRESS (see docs/OWNER-ACTIONS.md) and assign the bay again."
            ),
        )
        return None
    access = locker.issue_customer_access(db, order=order, bay_id=bay_id)
    resolve_open_exceptions(
        db, kind=PICKUP_NOT_CONFIGURED, reference_type="ORDER", reference_id=order.id,
        note="The pickup address was configured and the buyer's code was issued.",
    )
    enqueue(
        db, topic="commerce/orders", event_type="PICKUP_CODE_ISSUED", aggregate_type="ORDER",
        aggregate_id=order.id,
        # The code itself stays out of the outbox: this message is read by the edge and by
        # operators, and it only has to say that a credential exists and until when.
        payload={"order_id": order.id, "order_number": order.order_number, "bay_id": bay_id,
                 "access_id": access.id, "valid_until": access.valid_until.isoformat()},
        idempotency_key=f"pickup-code:{access.id}",
    )
    return access


def finalize_for_bay(db: Session, package: Package, bay_id: str):
    if package.state != "LABEL_VERIFIED" or not package.weight_g:
        raise OrderError("Package must have verified label and weight")
    package.bay_id = bay_id
    package.state = "READY_FOR_PICKUP"
    order = db.get(Order, package.order_id)
    order.state = "READY_FOR_PICKUP"
    enqueue(
        db, topic="warehouse/parcels", event_type="PARCEL_READY", aggregate_type="PACKAGE", aggregate_id=package.id,
        payload={"package_id": package.id, "order_id": order.id, "bay_id": bay_id, "weight_g": package.weight_g},
        idempotency_key=f"parcel-ready:{package.id}",
    )
    issue_pickup_code(db, order, bay_id)
    return package


def mark_handoff(db: Session, bay_id: str):
    packages = list(db.scalars(select(Package).where(Package.bay_id == bay_id, Package.state == "READY_FOR_PICKUP")))
    for package in packages:
        package.state = "HANDOFF_COMPLETE"
        order = db.get(Order, package.order_id)
        order.state = "HANDOFF_COMPLETE"
        reservations = list(db.scalars(select(Reservation).join(OrderLine).where(OrderLine.order_id == order.id, Reservation.state == "ACTIVE")))
        for r in reservations:
            ship_reserved(db, variant_id=r.variant_id, location_id=r.location_id, qty=r.qty, reference_id=r.order_line_id)
            r.state = "CONSUMED"
        # The parcel has left the bay, so the buyer's code stops opening it and the code
        # itself is erased from the row that carried it.
        locker.revoke_customer_access(db, order_id=order.id, reason="PARCEL_LEFT_THE_BAY")
        enqueue(
            db, topic="commerce/shipments", event_type="HANDOFF_COMPLETE", aggregate_type="PACKAGE", aggregate_id=package.id,
            payload={"package_id": package.id, "order_id": order.id, "bay_id": bay_id},
            idempotency_key=f"handoff:{package.id}",
        )
    return packages


SHIPPABLE_PACKAGE_STATES = {"PACKING", "LABEL_VERIFIED", "READY_FOR_PICKUP"}


def ship_order(db: Session, order: Order, *, carrier: str, tracking_code: str) -> Package:
    """Record that a parcel left with a carrier, with no locker involved.

    The operator types the carrier and the tracking code off the label they bought
    (Canada Post counter, EasyPost dashboard, anything). The package must be packed and
    weighed. A tracking code EasyPost already bound to this package is the only one
    accepted, the way label verification treats it.
    """
    carrier = (carrier or "").strip()
    tracking_code = (tracking_code or "").strip()
    if not carrier or not tracking_code:
        raise OrderError("Carrier and tracking code are both required")
    if (order.fulfillment_method or "") == "PICKUP":
        raise OrderError("This order was bought for locker pickup; it leaves through the locker handoff")
    package = db.scalar(select(Package).where(Package.order_id == order.id))
    if package is None:
        raise OrderError("Pack the order before shipping it")
    if package.state == "HANDOFF_COMPLETE":
        record = db.scalar(select(ShipmentRecord).where(ShipmentRecord.package_id == package.id))
        if record and record.tracking_code == tracking_code:
            return package  # the same request again
        raise OrderError("This parcel has already shipped")
    if package.state not in SHIPPABLE_PACKAGE_STATES:
        raise OrderError(f"Package is {package.state}; pack it before shipping")
    if not package.weight_g:
        raise OrderError("Weigh the package before shipping it")

    record = db.scalar(select(ShipmentRecord).where(ShipmentRecord.package_id == package.id))
    bound = bound_tracking_code(db, package)
    if bound and bound != tracking_code:
        raise OrderError(f"A label was bought for this package with tracking {bound}; ship it with that code")
    if record is None:
        record = ShipmentRecord(package_id=package.id, provider="MANUAL", state="SHIPPED")
        db.add(record)
    elif record.state != "PURCHASED":
        record.provider = "MANUAL"
        record.state = "SHIPPED"
    record.carrier = carrier[:80]
    record.tracking_code = tracking_code[:180]
    package.expected_label_code = package.expected_label_code or record.tracking_code
    package.state = "HANDOFF_COMPLETE"
    order.state = "HANDOFF_COMPLETE"
    for r in db.scalars(select(Reservation).join(OrderLine).where(OrderLine.order_id == order.id, Reservation.state == "ACTIVE")):
        ship_reserved(db, variant_id=r.variant_id, location_id=r.location_id, qty=r.qty, reference_id=r.order_line_id)
        r.state = "CONSUMED"
    db.flush()
    enqueue(
        db, topic="commerce/shipments", event_type="HANDOFF_COMPLETE", aggregate_type="PACKAGE", aggregate_id=package.id,
        payload={"package_id": package.id, "order_id": order.id, "carrier": record.carrier,
                 "tracking_code": record.tracking_code, "source": "manual"},
        idempotency_key=f"handoff:{package.id}",
    )
    return package
