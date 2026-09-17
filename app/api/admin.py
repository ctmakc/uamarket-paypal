from __future__ import annotations
import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..deps import get_db
from ..auth import require_admin, require_operator
from ..models import Bay, CourierPickup, Device, DeviceEvent, ExceptionRecord, InventoryBalance, Location, Mission, Order, OutboxMessage, Package, ShipmentRecord, Variant
from ..edge_models import EdgeCredential
from ..schemas import AccessVerifyIn, AssignBayIn, BayStateIn, CommissioningUnlockIn, DeviceEventIn, EdgeAckIn, EdgeEventIn, LabelVerifyIn, OrderWebhookIn, PickupBuyEasyPostIn, PickupIn, PickupScheduleEasyPostIn, ReceiptIn, ScanConfirmIn, ShipmentBuyIn, ShipmentQuoteIn, WeightIn
from ..services.inventory import InventoryError, get_variant_by_sku, receive
from ..services.locker import LockerError, close_after_pickup, issue_access, verify_and_open
from ..services.orders import OrderError, confirm_mission, create_package, finalize_for_bay, ingest_order, mark_handoff, reserve_order, resolve_exception, verify_label
from ..services.seed import seed
from ..services.rebuild import rebuild_balances
from ..services.outbox import acknowledge, pending
from ..services.shopify import ShopifyWebhookError, normalize_paid_order, verify_hmac
from ..services.easypost import EasyPostClient, EasyPostError
from ..services.edge_auth import revoke_credential, rotate_credential
from ..services.commissioning import CommissioningError, commissioning_snapshot, request_state_refresh, request_test_unlock

router = APIRouter()


@router.get("/health")
def health(request: Request):
    """Liveness and database reachability. 503 when the database does not answer SELECT 1."""
    from fastapi.responses import JSONResponse
    from ..db import ping
    try:
        ping(request.app.state.engine)
    except Exception as exc:  # noqa: BLE001 - any database failure is "not healthy"
        return JSONResponse({"ok": False, "database": "unreachable", "error": type(exc).__name__}, status_code=503)
    return {"ok": True, "service": "uamarket-api", "database": "ok"}

@router.post("/admin/seed", dependencies=[Depends(require_admin)])
def seed_endpoint(db: Session = Depends(get_db)):
    seed(db); db.commit()
    return {"ok": True}

@router.post("/admin/seed-catalog", dependencies=[Depends(require_admin)])
def seed_catalog_endpoint(with_stock: bool = True, with_media: bool = True, db: Session = Depends(get_db)):
    """Demo storefront catalogue (placeholder assortment) + demo stock + the generated
    demonstration pictures. Idempotent; a photo the owner uploaded is never replaced."""
    from ..services.catalog_seed import seed_catalog
    seed(db)
    result = seed_catalog(db, with_stock=with_stock, with_media=with_media); db.commit()
    return {"ok": True, **result}

@router.post("/admin/edge-devices/{device_id}/credentials/rotate", dependencies=[Depends(require_admin)])
def edge_credential_rotate(device_id: str, site: str = "default", db: Session = Depends(get_db)):
    credential, token = rotate_credential(db, device_id=device_id, site=site)
    db.commit()
    return {
        "device_id": credential.device_id, "site": credential.site,
        "enabled": credential.enabled, "token": token,
        "rotated_at": credential.rotated_at.isoformat(),
    }


@router.post("/admin/edge-devices/{device_id}/credentials/revoke", dependencies=[Depends(require_admin)])
def edge_credential_revoke(device_id: str, site: str = "default", db: Session = Depends(get_db)):
    credential = revoke_credential(db, device_id=device_id, site=site)
    if not credential:
        raise HTTPException(404, "Edge credential not found")
    db.commit()
    return {"device_id": device_id, "site": site, "enabled": False}


@router.get("/admin/edge-devices", dependencies=[Depends(require_admin)])
def edge_devices(db: Session = Depends(get_db)):
    rows = list(db.scalars(select(EdgeCredential).order_by(EdgeCredential.device_id, EdgeCredential.site)))
    return {"devices": [{
        "device_id": row.device_id, "site": row.site, "enabled": row.enabled,
        "created_at": row.created_at.isoformat(), "rotated_at": row.rotated_at.isoformat(),
        "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
    } for row in rows]}


@router.get("/admin/commissioning/locker/{device_id}", dependencies=[Depends(require_admin)])
def commissioning_locker_status(
    device_id: str, site: str = "default", event_limit: int = 100, stale_seconds: int = 30,
    db: Session = Depends(get_db),
):
    try:
        return commissioning_snapshot(
            db, device_id=device_id, site=site, event_limit=event_limit, stale_seconds=stale_seconds
        )
    except CommissioningError as exc:
        raise HTTPException(409, str(exc))


@router.post("/admin/commissioning/locker/{device_id}/{bay_id}/refresh", dependencies=[Depends(require_admin)])
def commissioning_locker_refresh(
    device_id: str, bay_id: str, site: str = "default", db: Session = Depends(get_db),
):
    try:
        msg = request_state_refresh(db, device_id=device_id, site=site, bay_id=bay_id)
        db.commit()
        return {"ok": True, "command_id": msg.id, "state": msg.state, "event_type": msg.event_type}
    except CommissioningError as exc:
        db.rollback()
        raise HTTPException(409, str(exc))


@router.post("/admin/commissioning/locker/{device_id}/{bay_id}/test-unlock", dependencies=[Depends(require_admin)])
def commissioning_locker_test_unlock(
    device_id: str, bay_id: str, inp: CommissioningUnlockIn, db: Session = Depends(get_db),
):
    try:
        msg = request_test_unlock(
            db, device_id=device_id, site=inp.site, bay_id=bay_id,
            ttl_seconds=inp.ttl_seconds, confirm=inp.confirm,
        )
        db.commit()
        return {"ok": True, "command_id": msg.id, "state": msg.state, "event_type": msg.event_type}
    except CommissioningError as exc:
        db.rollback()
        raise HTTPException(409, str(exc))


@router.post("/admin/rebuild-balances", dependencies=[Depends(require_admin)])
def rebuild_endpoint(db: Session = Depends(get_db)):
    try:
        event_count = rebuild_balances(db)
        db.commit()
        return {"ok": True, "events_replayed": event_count}
    except Exception as e:
        db.rollback()
        raise HTTPException(409, str(e))

@router.post("/v1/receipts", dependencies=[Depends(require_operator)])
def receipt(inp: ReceiptIn, db: Session = Depends(get_db)):
    try:
        variant = get_variant_by_sku(db, inp.sku)
        if not db.get(Location, inp.location_id):
            raise HTTPException(404, "Unknown location")
        receive(db, variant_id=variant.id, location_id=inp.location_id, qty=inp.qty, reference_id=inp.reference_id)
        db.commit()
        return {"ok": True, "sku": inp.sku, "qty": inp.qty, "location": inp.location_id}
    except InventoryError as e:
        db.rollback(); raise HTTPException(400, str(e))

@router.post("/webhooks/order", dependencies=[Depends(require_operator)])
def order_webhook(inp: OrderWebhookIn, db: Session = Depends(get_db)):
    payload = inp.model_dump()
    try:
        order, duplicate = ingest_order(db, payload)
        db.commit()
        return {"order_id": order.id, "state": order.state, "duplicate": duplicate}
    except (OrderError, IntegrityError) as e:
        db.rollback(); raise HTTPException(400, str(e))

@router.post("/webhooks/shopify/orders-paid")
async def shopify_orders_paid(request: Request, db: Session = Depends(get_db)):
    raw = await request.body()
    secret = os.getenv("SHOPIFY_CLIENT_SECRET", "")
    provided = request.headers.get("x-shopify-hmac-sha256", "")
    if not verify_hmac(raw, provided, secret):
        raise HTTPException(401, "Invalid Shopify HMAC")
    event_id = request.headers.get("x-shopify-webhook-id") or request.headers.get("x-shopify-event-id")
    if not event_id:
        raise HTTPException(400, "Missing Shopify webhook id")
    topic = request.headers.get("x-shopify-topic", "orders/paid")
    try:
        payload = normalize_paid_order(raw, event_id=event_id, topic=topic)
        order, duplicate = ingest_order(db, payload)
        db.commit()
        return {"order_id": order.id, "state": order.state, "duplicate": duplicate}
    except (ShopifyWebhookError, OrderError, IntegrityError) as exc:
        db.rollback()
        raise HTTPException(400, str(exc))


@router.get("/admin/outbox", dependencies=[Depends(require_admin)])
def outbox_view(db: Session = Depends(get_db)):
    rows = list(db.scalars(select(OutboxMessage).order_by(OutboxMessage.created_at.desc()).limit(100)))
    return {"messages": [{
        "id": m.id, "topic": m.topic, "event_type": m.event_type, "state": m.state,
        "aggregate_type": m.aggregate_type, "aggregate_id": m.aggregate_id,
        "attempt_count": m.attempt_count, "idempotency_key": m.idempotency_key,
    } for m in rows]}

class ExceptionResolveIn(BaseModel):
    """Body of POST /v1/exceptions/{id}/resolve. The note is what was done about the problem."""
    note: str = Field(min_length=1, max_length=2000)
    resolved_by: str | None = Field(default=None, max_length=120)


def _exception_row(record: ExceptionRecord) -> dict:
    return {
        "id": record.id, "kind": record.kind, "state": record.state,
        "reference_type": record.reference_type, "reference_id": record.reference_id,
        "details": record.details, "created_at": record.created_at.isoformat(),
        "resolution_note": record.resolution_note, "resolved_by": record.resolved_by,
        "resolved_at": record.resolved_at.isoformat() if record.resolved_at else None,
    }


@router.get("/v1/exceptions", dependencies=[Depends(require_operator)])
def exceptions_list(state: str = "OPEN", limit: int = 100, db: Session = Depends(get_db)):
    """List exceptions. `state=OPEN` (default), `state=RESOLVED`, or `state=ALL`."""
    wanted = (state or "OPEN").strip().upper()
    stmt = select(ExceptionRecord).order_by(ExceptionRecord.created_at.desc()).limit(max(1, min(limit, 500)))
    if wanted != "ALL":
        stmt = stmt.where(ExceptionRecord.state == wanted)
    rows = list(db.scalars(stmt))
    return {"state": wanted, "exceptions": [_exception_row(r) for r in rows]}


@router.post("/v1/exceptions/{exception_id}/resolve")
def exception_resolve(
    exception_id: str, inp: ExceptionResolveIn,
    db: Session = Depends(get_db), actor: str = Depends(require_operator),
):
    """Close one exception with a note saying what was done. Resolving twice is a no-op."""
    record = db.get(ExceptionRecord, exception_id)
    if not record:
        raise HTTPException(404, "Exception not found")
    if record.state == "RESOLVED":
        return {**_exception_row(record), "changed": False}
    resolve_exception(record, note=inp.note, resolved_by=inp.resolved_by or actor)
    db.commit()
    return {**_exception_row(record), "changed": True}


PAID_OR_LATER_STATES = ["PAID", "PICK_PLANNED", "PICKING", "PICK_VERIFIED", "PACKING", "LABEL_VERIFIED",
                        "READY_FOR_PICKUP", "HANDOFF_COMPLETE", "OUT_OF_STOCK"]


@router.get("/v1/dashboard", dependencies=[Depends(require_operator)])
def dashboard_json(db: Session = Depends(get_db)):
    orders_waiting = db.scalar(select(func.count()).select_from(Order).where(Order.state.in_(["PAID", "PICK_PLANNED", "PICKING", "PICK_VERIFIED", "PACKING", "LABEL_VERIFIED"]))) or 0
    exceptions_open = db.scalar(select(func.count()).select_from(ExceptionRecord).where(ExceptionRecord.state == "OPEN")) or 0
    exceptions_resolved = db.scalar(select(func.count()).select_from(ExceptionRecord).where(ExceptionRecord.state == "RESOLVED")) or 0
    exceptions_total = db.scalar(select(func.count()).select_from(ExceptionRecord)) or 0
    ready = db.scalar(select(func.count()).select_from(Package).where(Package.state == "READY_FOR_PICKUP")) or 0
    # Gross is money that arrived: orders that reached PAID or any later state, never an
    # unpaid or cancelled order. A web order counts from its paid_at; a channel order that is
    # created paid (Shopify) counts from its creation.
    day_ago = datetime.now(timezone.utc) - timedelta(days=1)
    gross = db.scalar(select(func.coalesce(func.sum(Order.gross_amount_cad), 0)).where(
        Order.state.in_(PAID_OR_LATER_STATES),
        func.coalesce(Order.paid_at, Order.created_at) >= day_ago,
    )) or 0
    stockout_risk = db.scalar(select(func.count()).select_from(InventoryBalance).where((InventoryBalance.qty_on_hand - InventoryBalance.qty_reserved) <= 2)) or 0
    awaiting_payment = db.scalar(select(func.count()).select_from(Order).where(Order.state == "AWAITING_PAYMENT")) or 0
    return {
        "orders_waiting": orders_waiting,
        # "exceptions" is the open count, kept under its old name for existing callers.
        "exceptions": exceptions_open,
        "exceptions_open": exceptions_open,
        "exceptions_resolved": exceptions_resolved,
        "exceptions_total": exceptions_total,
        "parcels_ready": ready,
        "gross_24h_cad": f"{float(gross):.2f}",
        "stockout_risk_locations": stockout_risk,
        "awaiting_payment": awaiting_payment,
    }


@router.get("/v1/inventory", dependencies=[Depends(require_operator)])
def inventory_json(db: Session = Depends(get_db)):
    """Balances per SKU and location, with the product name beside every SKU."""
    from ..models import Product
    rows = db.execute(
        select(Variant.sku, Variant.option_label, Product.title, InventoryBalance.location_id,
               InventoryBalance.qty_on_hand, InventoryBalance.qty_reserved)
        .join(InventoryBalance, InventoryBalance.variant_id == Variant.id)
        .outerjoin(Product, Product.id == Variant.product_id)
        .order_by(Product.title, Variant.sku, InventoryBalance.location_id)
    ).all()
    return {"items": [{
        "sku": sku, "product": title or None, "label": label, "location": loc,
        "on_hand": on, "reserved": res, "available": on - res,
    } for sku, label, title, loc, on, res in rows]}


@router.get("/", dependencies=[Depends(require_operator)])
def home():
    """The old header-key HTML dashboard is retired: the owner works at /admin on the storefront,
    behind a password and a session. This answers where to go instead."""
    return {"retired": True, "use": "/admin on the storefront", "json": ["/v1/dashboard", "/v1/inventory"]}
