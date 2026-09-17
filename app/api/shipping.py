from __future__ import annotations
import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..deps import get_db
from ..auth import require_operator
from ..models import Bay, CourierPickup, Device, DeviceEvent, ExceptionRecord, InventoryBalance, Location, Mission, Order, OutboxMessage, Package, ShipmentRecord, Variant, now_utc
from ..schemas import AccessVerifyIn, AssignBayIn, BayStateIn, DeviceEventIn, EdgeAckIn, EdgeEventIn, LabelVerifyIn, OrderWebhookIn, PickupBuyEasyPostIn, PickupIn, PickupScheduleEasyPostIn, ReceiptIn, ScanConfirmIn, ShipmentBuyIn, ShipmentQuoteIn, WeightIn
from ..services.inventory import InventoryError, get_variant_by_sku, receive
from ..services.locker import LockerError, close_after_pickup, issue_access, verify_and_open
from ..services.orders import OrderError, confirm_mission, create_package, finalize_for_bay, ingest_order, mark_handoff, open_exception, reserve_order, resolve_open_exceptions, verify_label
from ..services.seed import seed
from ..services.rebuild import rebuild_balances
from ..services.outbox import acknowledge, pending
from ..services.shopify import ShopifyWebhookError, normalize_paid_order, verify_hmac
from ..services.easypost import EasyPostClient, EasyPostError

router = APIRouter()

@router.post("/v1/packages/{package_id}/shipping/easypost/quote", dependencies=[Depends(require_operator)])
def easypost_quote(package_id: str, inp: ShipmentQuoteIn, db: Session = Depends(get_db)):
    package = db.get(Package, package_id)
    if not package:
        raise HTTPException(404, "Package not found")
    if not package.weight_g:
        raise HTTPException(409, "Package weight required before rating")
    existing = db.scalar(select(ShipmentRecord).where(ShipmentRecord.package_id == package.id))
    if existing and existing.external_shipment_id:
        return {
            "shipment_id": existing.id, "external_shipment_id": existing.external_shipment_id,
            "state": existing.state, "rates": json.loads(existing.rates_json or "[]"),
        }
    try:
        client = EasyPostClient(os.getenv("EASYPOST_API_KEY", ""))
        response = client.create_shipment(
            to_address=inp.to_address.model_dump(exclude_none=True),
            from_address=inp.from_address.model_dump(exclude_none=True),
            parcel={
                "length": inp.length_in, "width": inp.width_in, "height": inp.height_in,
                "weight": round(package.weight_g / 28.349523125, 2),
            },
            reference=package.id,
        )
    except EasyPostError as exc:
        raise HTTPException(502, str(exc))
    rates = response.get("rates") or []
    record = ShipmentRecord(
        package_id=package.id, provider="EASYPOST", external_shipment_id=response.get("id"),
        state="RATED", rates_json=json.dumps(rates),
    )
    db.add(record); db.commit(); db.refresh(record)
    return {"shipment_id": record.id, "external_shipment_id": record.external_shipment_id, "state": record.state, "rates": rates}

def _retrieve_shipment(client, shipment_id: str) -> dict:
    """Read a shipment back from EasyPost to learn whether a label was already bought."""
    getter = getattr(client, "retrieve_shipment", None)
    if getter is not None:
        return getter(shipment_id)
    request = getattr(client, "_request", None)
    if request is None:
        raise EasyPostError("This EasyPost client cannot read a shipment back")
    return request("GET", f"/shipments/{shipment_id}")


def _is_purchased(response: dict) -> bool:
    """A shipment carrying a tracking code or a postage label has been paid for."""
    label = response.get("postage_label") or {}
    return bool(response.get("tracking_code") or label.get("label_url") or label.get("label_zpl_url"))


def _apply_purchase(db: Session, record: ShipmentRecord, package: Package, response: dict, *, requested_rate_id: str) -> None:
    """Store an EasyPost purchase. Fields absent from the response keep the value already stored."""
    label = response.get("postage_label") or {}
    rate = response.get("selected_rate") or {}
    record.state = "PURCHASED"
    record.selected_rate_id = rate.get("id") or record.selected_rate_id or requested_rate_id
    record.carrier = rate.get("carrier") or record.carrier
    record.service = rate.get("service") or record.service
    record.tracking_code = response.get("tracking_code") or record.tracking_code
    record.label_url = label.get("label_url") or record.label_url
    record.label_zpl_url = label.get("label_zpl_url") or record.label_zpl_url
    if rate.get("rate") is not None:
        try:
            record.postage_amount = float(rate["rate"])
        except (TypeError, ValueError):
            record.postage_amount = None
    record.currency = rate.get("currency") or record.currency
    if record.purchase_started_at is None:
        record.purchase_started_at = now_utc()
    if record.tracking_code:
        package.expected_label_code = record.tracking_code


def _buy_response(record: ShipmentRecord) -> dict:
    return {
        "shipment_id": record.id, "tracking_code": record.tracking_code,
        "carrier": record.carrier, "service": record.service,
        "label_url": record.label_url, "label_zpl_url": record.label_zpl_url,
        "postage_amount": record.postage_amount, "currency": record.currency,
        "state": record.state,
    }


@router.post("/v1/packages/{package_id}/shipping/easypost/buy", dependencies=[Depends(require_operator)])
def easypost_buy(package_id: str, inp: ShipmentBuyIn, db: Session = Depends(get_db)):
    """Buy one postage label per package, at most once.

    `purchase_started_at` is written and committed before the buy leaves for EasyPost. If the call
    times out or the process dies before the response is stored, the marker survives, and the next
    attempt reads the shipment back from EasyPost instead of paying for a second label.
    """
    package = db.get(Package, package_id)
    if not package:
        raise HTTPException(404, "Package not found")
    record = db.scalar(select(ShipmentRecord).where(ShipmentRecord.package_id == package.id))
    if not record or not record.external_shipment_id:
        raise HTTPException(409, "Rate shipment first")
    if record.state == "PURCHASED" and record.tracking_code:
        return _buy_response(record)
    try:
        client = EasyPostClient(os.getenv("EASYPOST_API_KEY", ""))
    except EasyPostError as exc:
        raise HTTPException(502, str(exc))

    if record.purchase_started_at is not None:
        try:
            existing = _retrieve_shipment(client, record.external_shipment_id)
        except EasyPostError as exc:
            open_exception(
                db, kind="LABEL_BUY_UNRESOLVED", reference_type="PACKAGE", reference_id=package.id,
                details=(
                    f"A label purchase for EasyPost shipment {record.external_shipment_id} was started at "
                    f"{record.purchase_started_at.isoformat()} and its outcome is still unknown: {exc}"
                ),
            )
            db.commit()
            raise HTTPException(409, (
                "An earlier label purchase for this package is unresolved and EasyPost could not be "
                "reached to check it. Open the shipment in EasyPost before retrying."
            ))
        if _is_purchased(existing):
            _apply_purchase(db, record, package, existing, requested_rate_id=inp.rate_id)
            resolve_open_exceptions(
                db, kind="LABEL_BUY_UNRESOLVED", reference_type="PACKAGE", reference_id=package.id,
                note="The label bought by the earlier attempt was found in EasyPost and recorded.",
            )
            db.commit()
            return _buy_response(record)
        # EasyPost holds no label for this shipment, so the earlier attempt bought nothing.
        resolve_open_exceptions(
            db, kind="LABEL_BUY_UNRESOLVED", reference_type="PACKAGE", reference_id=package.id,
            note="EasyPost holds no label for this shipment, so no postage was paid for.",
        )

    record.purchase_started_at = now_utc()
    db.commit()
    try:
        response = client.buy_shipment(record.external_shipment_id, inp.rate_id)
    except EasyPostError as exc:
        raise HTTPException(502, str(exc))
    _apply_purchase(db, record, package, response, requested_rate_id=inp.rate_id)
    db.commit()
    return _buy_response(record)

@router.post("/v1/pickups/{pickup_id}/easypost/schedule", dependencies=[Depends(require_operator)])
def easypost_pickup_schedule(pickup_id: str, inp: PickupScheduleEasyPostIn, db: Session = Depends(get_db)):
    pickup = db.get(CourierPickup, pickup_id)
    package = db.get(Package, inp.package_id)
    if not pickup or not package:
        raise HTTPException(404, "Pickup or package not found")
    shipment = db.scalar(select(ShipmentRecord).where(ShipmentRecord.package_id == package.id))
    if not shipment or shipment.state != "PURCHASED" or not shipment.external_shipment_id:
        raise HTTPException(409, "Package needs a purchased EasyPost shipment")
    if pickup.external_pickup_id:
        return {"pickup_id": pickup.id, "external_pickup_id": pickup.external_pickup_id, "status": pickup.external_status, "rates": json.loads(pickup.external_rates_json or "[]")}
    try:
        client = EasyPostClient(os.getenv("EASYPOST_API_KEY", ""))
        response = client.create_pickup(
            address=inp.address.model_dump(exclude_none=True), shipment_id=shipment.external_shipment_id,
            carrier_accounts=inp.carrier_accounts, min_datetime=pickup.window_start.isoformat(),
            max_datetime=pickup.window_end.isoformat(), instructions=inp.instructions, reference=pickup.id,
        )
    except EasyPostError as exc:
        raise HTTPException(502, str(exc))
    rates = response.get("pickup_rates") or []
    pickup.external_pickup_id = response.get("id")
    pickup.external_status = response.get("status") or "created"
    pickup.external_rates_json = json.dumps(rates)
    db.commit()
    return {"pickup_id": pickup.id, "external_pickup_id": pickup.external_pickup_id, "status": pickup.external_status, "rates": rates}

@router.post("/v1/pickups/{pickup_id}/easypost/buy", dependencies=[Depends(require_operator)])
def easypost_pickup_buy(pickup_id: str, inp: PickupBuyEasyPostIn, db: Session = Depends(get_db)):
    pickup = db.get(CourierPickup, pickup_id)
    if not pickup or not pickup.external_pickup_id:
        raise HTTPException(409, "Create EasyPost pickup first")
    try:
        client = EasyPostClient(os.getenv("EASYPOST_API_KEY", ""))
        response = client.buy_pickup(pickup.external_pickup_id, inp.carrier, inp.service)
    except EasyPostError as exc:
        raise HTTPException(502, str(exc))
    pickup.external_status = response.get("status") or "scheduled"
    db.commit()
    return {"pickup_id": pickup.id, "external_pickup_id": pickup.external_pickup_id, "status": pickup.external_status}
