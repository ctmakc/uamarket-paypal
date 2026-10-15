"""The owner's PayPal desk: an agent in /admin that reads the shop and PayPal side by side.

It answers questions such as "which PayPal orders are paid and not shipped?", "did the
tracking for UA-… reach PayPal?", "any disputes?", "what did PayPal record for this
order?". Reads run immediately. Anything that changes money or PayPal records (pushing a
tracking number, refunding a cancelled order) comes back as a proposed action card; it
runs only when the owner presses Confirm, through the same endpoints the order page uses.

PayPal reads go through the official PayPal Agent Toolkit (paypal-agent-toolkit,
`PayPalAPI.run`), so the tool names and payloads are PayPal's own:
get_order_details, list_disputes, get_dispute, get_shipment_tracking, list_transactions.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import llm, paypal
from ..models import Order

log = logging.getLogger("uamarket.desk")

QUEUES = ("awaiting_payment", "to_pack", "ready_to_ship", "shipped", "exceptions", "cancelled")


def _toolkit():
    """The PayPal Agent Toolkit's framework-free entry point, with this shop's credentials."""
    from paypal_agent_toolkit.shared.api import PayPalAPI
    from paypal_agent_toolkit.shared.configuration import Context

    return PayPalAPI(client_id=paypal.client_id(), secret=paypal._secret(), context=Context(sandbox=paypal.sandbox()))


def toolkit_run(method: str, params: dict) -> dict:
    if not paypal.configured():
        return {"error": "PayPal is not configured"}
    try:
        raw = _toolkit().run(method, {k: v for k, v in params.items() if v is not None})
    except Exception as exc:  # the toolkit raises requests errors as-is
        status = getattr(getattr(exc, "response", None), "status_code", None)
        hint = " (PayPal: this app lacks the permission; enable it in the developer dashboard)" if status == 403 else ""
        return {"error": f"PayPal {method} failed{hint}: {str(exc)[:200]}"}
    try:
        return json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        return {"result": str(raw)[:4000]}


def _slim_paypal_order(data: dict) -> dict:
    raw = data.get("raw") if isinstance(data.get("raw"), dict) else data
    units = raw.get("purchase_units") or [{}]
    caps = ((units[0].get("payments") or {}).get("captures") or [])
    refunds = ((units[0].get("payments") or {}).get("refunds") or [])
    trackers = ((units[0].get("shipping") or {}).get("trackers") or [])
    payer = (raw.get("payment_source") or {}).get("paypal") or {}
    return {
        "id": raw.get("id"), "status": raw.get("status"), "invoice_id": units[0].get("invoice_id"),
        "amount": units[0].get("amount", {}).get("value"), "currency": units[0].get("amount", {}).get("currency_code"),
        "captures": [{"id": c.get("id"), "status": c.get("status"), "amount": (c.get("amount") or {}).get("value"),
                      "seller_protection": (c.get("seller_protection") or {}).get("status")} for c in caps],
        "refunds": [{"id": r.get("id"), "status": r.get("status"), "amount": (r.get("amount") or {}).get("value")} for r in refunds],
        "trackers": [{"id": t.get("id"), "status": t.get("status")} for t in trackers],
        "payer_country": (payer.get("address") or {}).get("country_code"),
        "payer_account_status": payer.get("account_status"),
    }


def system_prompt() -> str:
    today = datetime.now(timezone.utc).date().isoformat()
    env = "PayPal SANDBOX (test money)" if paypal.sandbox() else "PayPal LIVE"
    return f"""You are the PayPal desk assistant inside the owner's admin of UA Market, a small Canadian shop. Today is {today} (UTC). Payments run in {env}.

You help the owner keep the shop and PayPal in agreement: paid orders, captures, tracking numbers PayPal knows about, refunds, disputes.

Rules:
1. Answer only from tool results. Shop tools read the shop's database; paypal_* tools call PayPal through the PayPal Agent Toolkit. If a tool fails, say what failed in one line.
2. Order numbers look like UA-YYMMDD-XXXX. PayPal order ids are 17 characters; capture (transaction) ids are 17 characters.
3. You do not change anything yourself. To push a tracking number to PayPal or refund a cancelled order, call propose_action; the owner sees a card and confirms it.
4. Seller protection on PayPal needs tracking for shipped goods: point out shipped PayPal orders whose tracking PayPal does not have.
5. Be brief: short sentences or a compact list, at most 120 words. Amounts in CAD. Write in the language the owner writes in.
"""


@dataclass
class DeskSession:
    db: Session
    actions: list[dict] = field(default_factory=list)
    orders_seen: list[dict] = field(default_factory=list)


def _tools(s: DeskSession) -> list[llm.Tool]:
    from ..api.admin_orders import order_detail, orders_queue

    def shop_orders(args: dict) -> dict:
        queue = args.get("queue") if args.get("queue") in QUEUES else "to_pack"
        data = orders_queue(queue=queue, q=None, db=s.db)
        items = [{"order_number": i["order_number"], "state": i["state"], "paid_at": i["paid_at"],
                  "payment_method": i["payment_method"], "total_cad": i["total_cad"], "customer": i["customer_name"],
                  "province": i["province"], "demo": i["demo"]} for i in data["items"][:25]]
        if args.get("paypal_only"):
            items = [i for i in items if i["payment_method"] == "PAYPAL"]
        return {"queue": queue, "counts": data["counts"], "orders": items}

    def shop_order(args: dict) -> dict:
        number = str(args.get("order_number") or "").strip().upper()
        order = s.db.scalar(select(Order).where(Order.order_number == number))
        if not order:
            return {"error": f"No order {number}"}
        d = order_detail(s.db, order)
        out = {
            "order_number": number, "state": d["state"], "queue": d["queue"], "total_cad": d["totals"]["total_cad"],
            "payment": d["payment"], "shipment": d["shipment"], "next_step": (d.get("next") or {}).get("action"),
            "lines": [{"sku": l["sku"], "title": l["title"], "qty": l["qty"]} for l in d["lines"]],
            "open_problems": [{"kind": e["kind"], "summary": e.get("summary")} for e in d["exceptions"] if e.get("state") == "OPEN"],
            "customer": d["customer"]["name"], "demo": d["demo"],
        }
        s.orders_seen.append({"order_number": number, "id": order.id})
        return out

    def paypal_unsynced(args: dict) -> dict:
        rows = list(s.db.scalars(select(Order).where(Order.payment_method == "PAYPAL").order_by(Order.created_at.desc()).limit(200)))
        missing_tracking = [o.order_number for o in rows if o.state == "HANDOFF_COMPLETE" and o.paypal_capture_id and not o.paypal_tracking_id]
        refund_due = [o.order_number for o in rows if o.state == "CANCELLED" and o.paypal_capture_id and not o.paypal_refund_id]
        unpaid_approved = [o.order_number for o in rows if o.state == "AWAITING_PAYMENT" and o.paypal_status == "APPROVED"]
        paid_not_shipped = [o.order_number for o in rows if o.paid_at and o.state not in {"HANDOFF_COMPLETE", "CANCELLED"}]
        return {"shipped_without_paypal_tracking": missing_tracking, "cancelled_paid_not_refunded": refund_due,
                "approved_in_paypal_not_captured": unpaid_approved, "paid_not_shipped": paid_not_shipped,
                "paypal_orders_total": len(rows)}

    def paypal_get_order(args: dict) -> dict:
        pid = str(args.get("paypal_order_id") or "").strip()
        if not pid and args.get("order_number"):
            order = s.db.scalar(select(Order).where(Order.order_number == str(args["order_number"]).strip().upper()))
            pid = order.paypal_order_id if order else ""
        if not pid:
            return {"error": "Give a PayPal order id or a shop order number paid with PayPal."}
        data = toolkit_run("get_order_details", {"order_id": pid})
        return data if "error" in data else _slim_paypal_order(data)

    def paypal_list_disputes(args: dict) -> dict:
        data = toolkit_run("list_disputes", {"dispute_state": args.get("state"), "page_size": 10})
        if "error" in data:
            return data
        items = data.get("items") or []
        return {"count": len(items), "disputes": [{"id": d.get("dispute_id"), "reason": d.get("reason"), "status": d.get("status"),
                                                    "amount": (d.get("dispute_amount") or {}).get("value"), "created": d.get("create_time")}
                                                   for d in items]}

    def paypal_get_dispute(args: dict) -> dict:
        return toolkit_run("get_dispute", {"dispute_id": str(args.get("dispute_id") or "")})

    def paypal_get_tracking(args: dict) -> dict:
        tx = str(args.get("transaction_id") or "").strip()
        if not tx and args.get("order_number"):
            order = s.db.scalar(select(Order).where(Order.order_number == str(args["order_number"]).strip().upper()))
            tx = (order.paypal_capture_id if order else "") or ""
        if not tx:
            return {"error": "Give a capture (transaction) id or a shop order number paid with PayPal."}
        data = toolkit_run("get_shipment_tracking", {"transaction_id": tx})
        if "error" in data:
            return data
        return {"transaction_id": tx, "trackers": [{"tracking_number": t.get("tracking_number"), "carrier": t.get("carrier"),
                                                    "status": t.get("status"), "shipment_date": t.get("shipment_date")}
                                                   for t in data.get("trackers") or []]}

    def paypal_list_transactions(args: dict) -> dict:
        days = max(1, min(int(args.get("days") or 7), 31))
        end = datetime.now(timezone.utc)
        data = toolkit_run("list_transactions", {
            "start_date": (end - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end_date": end.strftime("%Y-%m-%dT%H:%M:%SZ"), "transaction_status": "S", "page_size": 50})
        if "error" in data:
            return data
        rows = data.get("transaction_details") or []
        return {"count": len(rows), "transactions": [{
            "id": (r.get("transaction_info") or {}).get("transaction_id"),
            "invoice_id": (r.get("transaction_info") or {}).get("invoice_id"),
            "amount": ((r.get("transaction_info") or {}).get("transaction_amount") or {}).get("value"),
            "status": (r.get("transaction_info") or {}).get("transaction_status"),
            "date": (r.get("transaction_info") or {}).get("transaction_initiation_date")} for r in rows[:30]],
            "note": "PayPal's transaction search can lag a few hours behind new payments."}

    def propose_action(args: dict) -> dict:
        kind = args.get("kind")
        number = str(args.get("order_number") or "").strip().upper()
        order = s.db.scalar(select(Order).where(Order.order_number == number))
        if not order:
            return {"error": f"No order {number}"}
        if order.payment_method != "PAYPAL" or not order.paypal_capture_id:
            return {"error": f"{number} was not captured through PayPal"}
        if kind == "push_tracking":
            from ..models import Package, ShipmentRecord
            package = s.db.scalar(select(Package).where(Package.order_id == order.id))
            record = s.db.scalar(select(ShipmentRecord).where(ShipmentRecord.package_id == package.id)) if package else None
            if order.state != "HANDOFF_COMPLETE" or not record or not record.tracking_code:
                return {"error": f"{number} has not shipped with a tracking number in the shop yet; ship it from the order page first."}
            if order.paypal_tracking_id:
                return {"error": f"PayPal already has tracking for {number} ({order.paypal_tracking_id})."}
            card = {"kind": "push_tracking", "order_id": order.id, "order_number": number, "carrier": record.carrier,
                    "tracking_number": record.tracking_code, "text": f"Send {record.carrier} {record.tracking_code} to PayPal for {number}"}
        elif kind == "refund":
            if order.state != "CANCELLED":
                return {"error": f"{number} is {order.state}; only a cancelled order is refunded from here."}
            if order.paypal_refund_id:
                return {"error": f"{number} was already refunded ({order.paypal_refund_id})."}
            card = {"kind": "refund", "order_id": order.id, "order_number": number,
                    "amount_cad": round(float(order.gross_amount_cad or 0), 2),
                    "text": f"Refund CA$ {float(order.gross_amount_cad or 0):.2f} through PayPal for {number}"}
        else:
            return {"error": "kind must be push_tracking or refund"}
        s.actions.append(card)
        return {"ok": True, "shown_to_owner": card["text"] + " (waits for the owner's Confirm)"}

    return [
        llm.Tool("shop_orders", "List the shop's orders in one admin queue, with counts for every queue.",
                 {"type": "object", "properties": {"queue": {"type": "string", "enum": list(QUEUES)},
                                                    "paypal_only": {"type": "boolean"}}}, shop_orders),
        llm.Tool("shop_order", "One shop order by number: state, totals, PayPal ids and status, shipment, open problems.",
                 {"type": "object", "properties": {"order_number": {"type": "string"}}, "required": ["order_number"]}, shop_order),
        llm.Tool("paypal_reconcile", "Where the shop and PayPal disagree: shipped without PayPal tracking, cancelled but not refunded, approved but not captured, paid but not shipped.",
                 {"type": "object", "properties": {}}, paypal_unsynced),
        llm.Tool("paypal_get_order", "PayPal's record of an order (PayPal Agent Toolkit get_order_details): status, captures, refunds, trackers, seller protection.",
                 {"type": "object", "properties": {"paypal_order_id": {"type": "string"}, "order_number": {"type": "string"}}}, paypal_get_order),
        llm.Tool("paypal_list_disputes", "Open PayPal disputes (PayPal Agent Toolkit list_disputes).",
                 {"type": "object", "properties": {"state": {"type": "string", "enum": ["REQUIRED_ACTION", "REQUIRED_OTHER_PARTY_ACTION", "UNDER_PAYPAL_REVIEW", "RESOLVED", "OPEN_INQUIRIES", "APPEALABLE"]}}},
                 paypal_list_disputes),
        llm.Tool("paypal_get_dispute", "One PayPal dispute in detail (PayPal Agent Toolkit get_dispute).",
                 {"type": "object", "properties": {"dispute_id": {"type": "string"}}, "required": ["dispute_id"]}, paypal_get_dispute),
        llm.Tool("paypal_get_tracking", "Tracking numbers PayPal has for a capture (PayPal Agent Toolkit get_shipment_tracking).",
                 {"type": "object", "properties": {"transaction_id": {"type": "string"}, "order_number": {"type": "string"}}}, paypal_get_tracking),
        llm.Tool("paypal_list_transactions", "Completed PayPal transactions over the last N days (PayPal Agent Toolkit list_transactions).",
                 {"type": "object", "properties": {"days": {"type": "integer", "minimum": 1, "maximum": 31}}}, paypal_list_transactions),
        llm.Tool("propose_action", "Propose a change for the owner to confirm: push_tracking (send a shipped order's tracking to PayPal) or refund (refund a cancelled PayPal order).",
                 {"type": "object", "properties": {"kind": {"type": "string", "enum": ["push_tracking", "refund"]},
                                                    "order_number": {"type": "string"}}, "required": ["kind", "order_number"]}, propose_action),
    ]


def chat(db: Session, *, messages: list[dict]) -> dict:
    history = []
    for m in (messages or [])[-14:]:
        if m.get("role") in {"user", "assistant"} and str(m.get("content") or "").strip():
            history.append({"role": m["role"], "content": str(m["content"])[:1500]})
    if not history or history[-1]["role"] != "user":
        raise ValueError("The last message must come from the owner")
    s = DeskSession(db=db)
    turn = llm.run(system_prompt(), history, _tools(s), max_rounds=7)
    return {"reply": turn.reply, "actions": s.actions, "trace": turn.trace, "model": llm.model(), "sandbox": paypal.sandbox()}
