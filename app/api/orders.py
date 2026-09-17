from __future__ import annotations
import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..deps import get_db
from ..auth import require_operator
from ..models import Bay, CourierPickup, Device, DeviceEvent, ExceptionRecord, InventoryBalance, Location, LockerAccess, Mission, Order, OutboxMessage, Package, ShipmentRecord, Variant
from ..schemas import AccessVerifyIn, AssignBayIn, BayStateIn, DeviceEventIn, EdgeAckIn, EdgeEventIn, LabelVerifyIn, OrderWebhookIn, PickupBuyEasyPostIn, PickupIn, PickupScheduleEasyPostIn, ReceiptIn, ScanConfirmIn, ShipmentBuyIn, ShipmentQuoteIn, WeightIn
from ..services.inventory import InventoryError, get_variant_by_sku, receive
from ..services.locker import (
    LockerError, burn_verify, close_after_pickup, issue_access, issue_customer_access,
    live_customer_access, pickup_address, revoke_customer_access, verify_and_open,
    verify_and_open_customer,
)
from ..services.ratelimit import (
    client_address, courier_attempt_limits, courier_ip_lockout, courier_ip_policy,
    courier_pin_limiter, courier_pin_policy, pickup_pin_lockout,
)
from ..services.orders import (
    PICKUP_NOT_CONFIGURED, OrderError, confirm_mission, create_package, finalize_for_bay, ingest_order,
    mark_handoff, reserve_order, resolve_open_exceptions, verify_label,
)
from ..services.storefront import notify_order
from ..services.seed import seed
from ..services.rebuild import rebuild_balances
from ..services.outbox import acknowledge, enqueue, pending
from ..services.shopify import ShopifyWebhookError, normalize_paid_order, verify_hmac
from ..services.easypost import EasyPostClient, EasyPostError

router = APIRouter()
log = logging.getLogger("uamarket.pickup")

# Bay booleans that describe physical hardware. Only the edge/PLC may report them true;
# see bay_state() below and app/api/edge.py:apply_edge_event().
EDGE_OWNED_BAY_FIELDS = ("inner_gate_closed", "outer_door_closed", "outer_door_locked")

# Both doors and the storefront limiters read the caller's address through
# services/ratelimit.client_address, which believes `X-Forwarded-For` only from a proxy
# named in TRUSTED_PROXY_IPS. One reading, so the guards cannot disagree.


@router.post("/v1/orders/{order_id}/reserve", dependencies=[Depends(require_operator)])
def reserve_endpoint(order_id: str, db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if not order: raise HTTPException(404, "Order not found")
    try:
        missions = reserve_order(db, order)
        db.commit()
        return {"order_id": order.id, "state": order.state, "missions": [{"id": m.id, "location": m.location_id, "qty": m.qty} for m in missions]}
    except InventoryError as e:
        db.commit()
        raise HTTPException(409, str(e))

@router.post("/v1/missions/{mission_id}/scan-confirm", dependencies=[Depends(require_operator)])
def scan_confirm(mission_id: str, inp: ScanConfirmIn, db: Session = Depends(get_db)):
    mission = db.get(Mission, mission_id)
    if not mission: raise HTTPException(404, "Mission not found")
    confirm_mission(db, mission, inp.barcode)
    db.commit()
    if mission.state == "WRONG_SKU": raise HTTPException(409, "WRONG_SKU")
    return {"mission_id": mission.id, "state": mission.state}

@router.post("/v1/orders/{order_id}/pack", dependencies=[Depends(require_operator)])
def pack(order_id: str, db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if not order: raise HTTPException(404, "Order not found")
    try:
        package = create_package(db, order); db.commit()
        return {"package_id": package.id, "state": package.state}
    except OrderError as e:
        db.rollback(); raise HTTPException(409, str(e))

@router.post("/v1/packages/{package_id}/weight", dependencies=[Depends(require_operator)])
def package_weight(package_id: str, inp: WeightIn, db: Session = Depends(get_db)):
    package = db.get(Package, package_id)
    if not package: raise HTTPException(404, "Package not found")
    package.weight_g = inp.weight_g; db.commit()
    return {"package_id": package.id, "weight_g": package.weight_g}

@router.post("/v1/packages/{package_id}/label-verify", dependencies=[Depends(require_operator)])
def package_label(package_id: str, inp: LabelVerifyIn, db: Session = Depends(get_db)):
    package = db.get(Package, package_id)
    if not package: raise HTTPException(404, "Package not found")
    ok = verify_label(db, package, inp.expected_label_code, inp.scanned_label_code); db.commit()
    if not ok: raise HTTPException(409, "LABEL_FAIL")
    return {"package_id": package.id, "state": package.state}

@router.post("/v1/packages/{package_id}/assign-bay", dependencies=[Depends(require_operator)])
def assign_bay(package_id: str, inp: AssignBayIn, db: Session = Depends(get_db)):
    package = db.get(Package, package_id); bay = db.get(Bay, inp.bay_id)
    if not package or not bay: raise HTTPException(404, "Package or bay not found")
    if not bay.inner_gate_closed: raise HTTPException(409, "Bay inner gate open")
    try:
        finalize_for_bay(db, package, bay.id); bay.weight_g += package.weight_g or 0; db.commit()
    except OrderError as e:
        db.rollback(); raise HTTPException(409, str(e))
    body = {"package_id": package.id, "state": package.state, "bay_id": bay.id}
    order = db.get(Order, package.order_id)
    access = live_customer_access(db, order.id) if order else None
    if access is not None:
        # The buyer's own code. The email goes out after the commit, the same way the other
        # order emails do, so a mail server that is down cannot undo a parcel already in a
        # bay. The code is handed back here as well: while SMTP is unconfigured the person
        # packing the parcel is the only one who can pass it on.
        result = notify_order(db, order, "pickup_ready")
        body["customer_pickup"] = _customer_pickup_body(order, access, emailed=bool(result and result.sent))
    return body

def _customer_pickup_body(order: Order, access: LockerAccess, *, emailed: bool) -> dict:
    """What the operator is handed when a buyer's code is minted. One shape, two routes."""
    return {
        "order_number": order.order_number,
        "bay_id": access.bay_id,
        "code": access.display_code,
        "valid_until": access.valid_until.isoformat(),
        "emailed": emailed,
    }


@router.post("/v1/packages/{package_id}/pickup-code", dependencies=[Depends(require_operator)])
def reissue_pickup_code(package_id: str, db: Session = Depends(get_db)):
    """Mint a fresh bay code for a parcel that is already in the locker.

    A code lives for `PICKUP_CODE_VALID_HOURS` and the parcel it belongs to can outlive it.
    The order page, the FAQ, the shipping page and both emails all tell the buyer a new one
    can be asked for, and until this route existed nothing could give them one: assigning
    the bay a second time is refused, because the parcel is already in it.

    So this is the operator's answer to "my code stopped working". It withdraws whatever
    the buyer was holding, mints one code for the bay the parcel is actually in, sends the
    "your parcel is in the locker" email again, and hands the digits back the way
    assign-bay does — while SMTP is off, the person at the locker is the one who passes
    them on.
    """
    package = db.get(Package, package_id)
    if not package:
        raise HTTPException(404, "Package not found")
    if package.state != "READY_FOR_PICKUP" or not package.bay_id:
        raise HTTPException(409, "This parcel is not in a bay, so there is no bay to open. Assign a bay first.")
    order = db.get(Order, package.order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    if order.channel != "WEB" or (order.fulfillment_method or "") != "PICKUP":
        raise HTTPException(409, "This order was not bought for locker pickup, so it has no customer code.")
    if not db.get(Bay, package.bay_id):
        raise HTTPException(404, "Package or bay not found")
    if not pickup_address():
        raise HTTPException(409, "PICKUP_ADDRESS is empty, so a code would reach the buyer with no building to take it to. Set it first (docs/OWNER-ACTIONS.md).")

    # A code that was already spent at the door is left as it stands: it opens nothing, and
    # it is the record that somebody opened this bay, which an operator needs to complete
    # the handoff afterwards.
    revoke_customer_access(db, order_id=order.id, reason="CODE_REISSUED", unspent_only=True)
    access = issue_customer_access(db, order=order, bay_id=package.bay_id)
    # This route is also how a parcel that reached a bay while the address was still empty
    # gets its code once the address is set, so it closes that alert the way minting at
    # bay assignment does.
    resolve_open_exceptions(
        db, kind=PICKUP_NOT_CONFIGURED, reference_type="ORDER", reference_id=order.id,
        note="The pickup address was configured and a code was issued for the bay the parcel is in.",
    )
    enqueue(
        db, topic="commerce/orders", event_type="PICKUP_CODE_ISSUED", aggregate_type="ORDER",
        aggregate_id=order.id,
        # The code itself stays out of the outbox here too; this only says a credential
        # exists, for which bay, and until when.
        payload={"order_id": order.id, "order_number": order.order_number, "bay_id": package.bay_id,
                 "access_id": access.id, "valid_until": access.valid_until.isoformat(),
                 "reissued": True},
        idempotency_key=f"pickup-code:{access.id}",
    )
    db.commit()
    # After the commit, the way every other order email goes out: a mail server that is
    # down cannot undo a code the buyer's page is already printing.
    result = notify_order(db, order, "pickup_ready", resend=True)
    return {
        "package_id": package.id,
        "state": package.state,
        "bay_id": package.bay_id,
        "customer_pickup": _customer_pickup_body(order, access, emailed=bool(result and result.sent)),
    }


@router.post("/v1/pickups", dependencies=[Depends(require_operator)])
def pickup_create(inp: PickupIn, db: Session = Depends(get_db)):
    if not db.get(Bay, inp.bay_id): raise HTTPException(404, "Bay not found")
    p = CourierPickup(carrier=inp.carrier, bay_id=inp.bay_id, window_start=inp.window_start, window_end=inp.window_end)
    db.add(p); db.flush(); pin = issue_access(db, p); db.commit()
    return {"pickup_id": p.id, "state": p.state, "pin": pin}

def _too_many(retry_after: float, message: str) -> HTTPException:
    return HTTPException(429, message, headers={"Retry-After": str(max(1, int(retry_after) + 1))})


def _record_pin_failure(db: Session, *, pickup_id: str, client_ip: str, reason: str) -> None:
    """Count one failed courier attempt and write an exception when a lockout trips."""
    pin_policy = courier_pin_policy()
    ip_policy = courier_ip_policy()
    pickup_locked = pickup_pin_lockout.register_failure(pickup_id, pin_policy)
    ip_locked = courier_ip_lockout.register_failure(client_ip, ip_policy)
    if pickup_locked:
        db.add(ExceptionRecord(
            kind="COURIER_PIN_LOCKOUT", reference_type="PICKUP", reference_id=pickup_id[:120],
            details=json.dumps({
                "summary": "Courier PIN entry locked after repeated failures",
                "failed_attempts": pin_policy.max_failures,
                "lockout_seconds": pin_policy.lockout_seconds,
                "last_failure": reason,
                "client_ips": [client_ip],
                "unlock_endpoint": f"/v1/pickups/{pickup_id}/access/unlock",
            }),
        ))
    if ip_locked:
        db.add(ExceptionRecord(
            kind="COURIER_PIN_IP_LOCKOUT", reference_type="CLIENT_IP", reference_id=client_ip,
            details=json.dumps({
                "summary": "Courier PIN entry locked for this client address",
                "failed_attempts": ip_policy.max_failures,
                "lockout_seconds": ip_policy.lockout_seconds,
                "last_failure": reason,
                "last_pickup_id": pickup_id,
            }),
        ))


@router.post("/courier/access/verify")
def access_verify(inp: AccessVerifyIn, request: Request, db: Session = Depends(get_db)):
    client_ip = client_address(request)
    attempts, window = courier_attempt_limits()
    if not courier_pin_limiter.allow(client_ip, limit=attempts, window=window):
        raise _too_many(window, "Too many PIN attempts from this address")
    for lockout, key, label in (
        (pickup_pin_lockout, inp.pickup_id, "This pickup is locked after repeated failed PIN entries"),
        (courier_ip_lockout, client_ip, "PIN entry from this address is locked after repeated failures"),
    ):
        retry = lockout.retry_after(key)
        if retry is not None:
            raise _too_many(retry, f"{label}. Ask the shop to unlock it.")
    try:
        bay = verify_and_open(db, inp.pickup_id, inp.pin)
    except LockerError as e:
        db.rollback()
        _record_pin_failure(db, pickup_id=inp.pickup_id, client_ip=client_ip, reason=str(e))
        db.commit()
        raise HTTPException(403, str(e))
    pickup_pin_lockout.clear(inp.pickup_id)
    courier_ip_lockout.clear(client_ip)
    db.commit()
    return {"ok": True, "bay_id": bay.id, "outer_door_locked": bay.outer_door_locked}


@router.post("/v1/pickups/{pickup_id}/access/unlock", dependencies=[Depends(require_operator)])
def pickup_access_unlock(pickup_id: str, db: Session = Depends(get_db)):
    """Operator recovery for a pickup whose PIN entry was locked out.

    Clears the pickup counter, clears the client addresses named in the open lockout
    exceptions, and closes those exceptions. The PIN itself is unchanged; issue a new
    pickup if the old PIN is believed to be known by someone else.
    """
    pickup = db.get(CourierPickup, pickup_id)
    if not pickup:
        raise HTTPException(404, "Pickup not found")
    unlocked = pickup_pin_lockout.clear(pickup_id)
    rows = list(db.scalars(select(ExceptionRecord).where(
        ExceptionRecord.kind == "COURIER_PIN_LOCKOUT",
        ExceptionRecord.reference_id == pickup_id,
        ExceptionRecord.state == "OPEN",
    )))
    cleared_ips: list[str] = []
    for row in rows:
        try:
            details = json.loads(row.details)
        except ValueError:
            details = {}
        for ip in details.get("client_ips") or []:
            courier_ip_lockout.clear(ip)
            courier_pin_limiter.clear(ip)
            if ip not in cleared_ips:
                cleared_ips.append(ip)
        row.state = "RESOLVED"
    if cleared_ips:
        for ip_row in db.scalars(select(ExceptionRecord).where(
            ExceptionRecord.kind == "COURIER_PIN_IP_LOCKOUT",
            ExceptionRecord.reference_id.in_(cleared_ips),
            ExceptionRecord.state == "OPEN",
        )):
            ip_row.state = "RESOLVED"
    db.commit()
    return {
        "pickup_id": pickup_id,
        "unlocked": unlocked or bool(rows),
        "cleared_client_ips": cleared_ips,
        "resolved_exceptions": [row.id for row in rows],
    }

# ------------------------------------------------------------------ customer pickup
#
# The buyer's door. It carries the same three guards as the courier's: a traffic cap per
# client address, a lockout per credential, and a lockout per address — the same counters,
# so an address that guesses is shut out of both doors at once. What it does NOT share is
# the credential: this route reads CUSTOMER rows only and cannot open a bay for a courier,
# and /courier/access/verify reads COURIER rows only and cannot open a bay for a buyer.
#
# Nor does it share the courier's answers. A courier stands at the locker with a phone
# number for the shop, so telling them their PIN is outside its window is help. This door
# is on the open internet and its first field is an order number, so every refusal here
# gives the same sentence: an order number that exists and one that does not, a code that
# is wrong and one that expired an hour ago, all read alike from outside. The reason is
# written to the log and, when a lockout trips, into the exception the operator sees.

CUSTOMER_DOOR_REFUSED = (
    "This code does not open a bay. Check the order number and the code on your order page, "
    "and write to the shop if the code has expired."
)


class CustomerAccessVerifyIn(BaseModel):
    order_number: str = Field(min_length=3, max_length=32)
    pin: str = Field(min_length=4, max_length=12)


def _customer_lock_key(order_number: str) -> str:
    return f"order:{order_number}"


def _record_customer_pin_failure(db: Session, *, order_number: str, client_ip: str, reason: str) -> None:
    """Count one failed buyer attempt and write an exception when a lockout trips."""
    pin_policy = courier_pin_policy()
    ip_policy = courier_ip_policy()
    order_locked = pickup_pin_lockout.register_failure(_customer_lock_key(order_number), pin_policy)
    ip_locked = courier_ip_lockout.register_failure(client_ip, ip_policy)
    if order_locked:
        db.add(ExceptionRecord(
            kind="CUSTOMER_PIN_LOCKOUT", reference_type="ORDER", reference_id=order_number[:120],
            details=json.dumps({
                "summary": "Locker code entry locked after repeated failures",
                "failed_attempts": pin_policy.max_failures,
                "lockout_seconds": pin_policy.lockout_seconds,
                "last_failure": reason,
                "client_ips": [client_ip],
                "unlock_endpoint": f"/v1/pickup-access/{order_number}/unlock",
            }),
        ))
    if ip_locked:
        db.add(ExceptionRecord(
            kind="CUSTOMER_PIN_IP_LOCKOUT", reference_type="CLIENT_IP", reference_id=client_ip,
            details=json.dumps({
                "summary": "Locker code entry locked for this client address",
                "failed_attempts": ip_policy.max_failures,
                "lockout_seconds": ip_policy.lockout_seconds,
                "last_failure": reason,
                "last_order_number": order_number,
            }),
        ))


@router.post("/pickup/access/verify")
def customer_access_verify(inp: CustomerAccessVerifyIn, request: Request, db: Session = Depends(get_db)):
    client_ip = client_address(request)
    attempts, window = courier_attempt_limits()
    if not courier_pin_limiter.allow(client_ip, limit=attempts, window=window):
        raise _too_many(window, "Too many code attempts from this address")
    order_number = inp.order_number.strip().upper()[:32]
    for lockout, key, label in (
        (pickup_pin_lockout, _customer_lock_key(order_number), "This order is locked after repeated failed code entries"),
        (courier_ip_lockout, client_ip, "Code entry from this address is locked after repeated failures"),
    ):
        retry = lockout.retry_after(key)
        if retry is not None:
            raise _too_many(retry, f"{label}. Ask the shop to unlock it.")
    order = db.scalar(select(Order).where(Order.order_number == order_number))
    try:
        if order is None or order.channel != "WEB" or (order.fulfillment_method or "") != "PICKUP":
            # An unknown order number is answered exactly like a wrong code, counted
            # exactly like one, and takes exactly as long: burn_verify pays for the key
            # derivation this branch would otherwise skip.
            burn_verify(inp.pin)
            raise LockerError("No access credential")
        bay = verify_and_open_customer(db, order, inp.pin)
    except LockerError as e:
        db.rollback()
        _record_customer_pin_failure(db, order_number=order_number, client_ip=client_ip, reason=str(e))
        db.commit()
        # The only place the real reason is written down, beside the exception a lockout
        # raises. The caller is told nothing but CUSTOMER_DOOR_REFUSED.
        log.info("pickup door refused order=%s address=%s reason=%s", order_number, client_ip, e)
        raise HTTPException(403, CUSTOMER_DOOR_REFUSED)
    pickup_pin_lockout.clear(_customer_lock_key(order_number))
    courier_ip_lockout.clear(client_ip)
    db.commit()
    return {"ok": True, "bay_id": bay.id, "outer_door_locked": bay.outer_door_locked}


@router.post("/v1/pickup-access/{order_number}/unlock", dependencies=[Depends(require_operator)])
def customer_access_unlock(order_number: str, db: Session = Depends(get_db)):
    """Operator recovery for a buyer whose code entry was locked out.

    Clears the counter for this order, clears the client addresses named in the open
    lockout exceptions, and closes those exceptions. The code itself is unchanged; assign
    the bay again if the old code is believed to be known by somebody else.
    """
    order_number = order_number.strip().upper()[:32]
    order = db.scalar(select(Order).where(Order.order_number == order_number))
    if not order:
        raise HTTPException(404, "Order not found")
    unlocked = pickup_pin_lockout.clear(_customer_lock_key(order_number))
    rows = list(db.scalars(select(ExceptionRecord).where(
        ExceptionRecord.kind == "CUSTOMER_PIN_LOCKOUT",
        ExceptionRecord.reference_id == order_number,
        ExceptionRecord.state == "OPEN",
    )))
    cleared_ips: list[str] = []
    for row in rows:
        try:
            details = json.loads(row.details)
        except ValueError:
            details = {}
        for ip in details.get("client_ips") or []:
            courier_ip_lockout.clear(ip)
            courier_pin_limiter.clear(ip)
            if ip not in cleared_ips:
                cleared_ips.append(ip)
        row.state = "RESOLVED"
    if cleared_ips:
        for ip_row in db.scalars(select(ExceptionRecord).where(
            ExceptionRecord.kind == "CUSTOMER_PIN_IP_LOCKOUT",
            ExceptionRecord.reference_id.in_(cleared_ips),
            ExceptionRecord.state == "OPEN",
        )):
            ip_row.state = "RESOLVED"
    db.commit()
    return {
        "order_number": order_number,
        "unlocked": unlocked or bool(rows),
        "cleared_client_ips": cleared_ips,
        "resolved_exceptions": [row.id for row in rows],
    }


def _customer_opened(db: Session, bay_id: str) -> list[LockerAccess]:
    """Customer credentials that were spent on this bay and whose parcel is still in it."""
    return list(db.scalars(select(LockerAccess).where(
        LockerAccess.kind == "CUSTOMER",
        LockerAccess.bay_id == bay_id,
        LockerAccess.used_at.is_not(None),
        LockerAccess.revoked_at.is_(None),
    )))


@router.post("/v1/bays/{bay_id}/handoff", dependencies=[Depends(require_operator)])
def handoff(bay_id: str, db: Session = Depends(get_db)):
    bay = db.get(Bay, bay_id)
    if not bay: raise HTTPException(404, "Bay not found")
    pickups = list(db.scalars(select(CourierPickup).where(CourierPickup.bay_id == bay.id, CourierPickup.state == "COURIER_OPEN")))
    # A bay can also be emptied by the buyer who owns what is in it: a customer credential
    # that has been spent on this bay is the same kind of proof that somebody stood at the
    # door and it opened for them.
    collected = _customer_opened(db, bay.id)
    if not pickups and not collected:
        raise HTTPException(409, "No confirmed courier-open or customer-open session for this bay")
    try:
        close_after_pickup(db, bay)
    except LockerError as exc:
        db.rollback()
        raise HTTPException(409, str(exc))
    packages = mark_handoff(db, bay.id)
    for p in pickups:
        p.state = "HANDOFF_COMPLETE"
    db.commit()
    return {"ok": True, "packages": [p.id for p in packages]}

@router.post("/v1/bays/{bay_id}/state", dependencies=[Depends(require_operator)])
def bay_state(bay_id: str, inp: BayStateIn, db: Session = Depends(get_db)):
    """Read bay state, and let an operator force a bay shut.

    The gate and door booleans are a projection of hardware sensors. Only the edge/PLC
    writes them true, through /edge/events. An operator may push one of them to false —
    a manual safety hold that takes the bay out of service and is written to the
    exception list — and nothing more, because every downstream precondition (assign
    bay, PIN unlock, handoff) requires true. So this route can no longer open a door the
    hardware refused to open.
    """
    bay = db.get(Bay, bay_id)
    if not bay: raise HTTPException(404, "Bay not found")
    holds: list[str] = []
    for field, value in inp.model_dump(exclude_none=True).items():
        if field in EDGE_OWNED_BAY_FIELDS:
            if bool(value):
                raise HTTPException(409, f"{field} is reported by the locker edge, not by the operator API. Send the sensor event from the edge device.")
            if getattr(bay, field) is not False:
                holds.append(field)
            setattr(bay, field, False)
        else:
            setattr(bay, field, value)
    if holds:
        db.add(ExceptionRecord(
            kind="BAY_MANUAL_HOLD", reference_type="BAY", reference_id=bay.id,
            details=json.dumps({
                "summary": "Operator forced bay interlock fields to false",
                "fields": holds,
                "note": "The edge device must report the sensors before this bay can be used again.",
            }),
        ))
    db.commit(); return {"id": bay.id, "inner_gate_closed": bay.inner_gate_closed, "outer_door_closed": bay.outer_door_closed, "outer_door_locked": bay.outer_door_locked, "weight_g": bay.weight_g}

@router.post("/v1/devices/{device_id}/event", dependencies=[Depends(require_operator)])
def device_event(device_id: str, inp: DeviceEventIn, db: Session = Depends(get_db)):
    dev = db.get(Device, device_id)
    if not dev: raise HTTPException(404, "Device not found")
    dev.last_seen_at = datetime.now(timezone.utc)
    db.add(DeviceEvent(device_id=device_id, event_type=inp.event_type, payload_json=json.dumps(inp.payload)))
    db.commit(); return {"ok": True}
