"""Run the Phase A flow entirely in-process without external integrations or hardware."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import create_app


def must(resp, label):
    if resp.status_code >= 300:
        raise RuntimeError(f"{label}: {resp.status_code} {resp.text}")
    data = resp.json()
    print(f"{label:22} -> {data}")
    return data


def main():
    db_path = ROOT / "demo.db"
    if db_path.exists():
        db_path.unlink()
    app = create_app(f"sqlite:///{db_path}")
    c = TestClient(app)
    must(c.post("/admin/seed"), "seed")
    must(c.post("/v1/receipts", json={"sku":"UA-W-BLACK-M","location_id":"A-LANE-01","qty":5,"reference_id":"DEMO-PO-001"}), "receive")
    order = must(c.post("/webhooks/order", json={"source":"demo","event_id":"demo-event-1","channel":"SHOPIFY","external_order_id":"DEMO-ORDER-001","lines":[{"sku":"UA-W-BLACK-M","qty":1,"unit_price_cad":79.99}]}), "ingest order")
    reservation = must(c.post(f"/v1/orders/{order['order_id']}/reserve"), "reserve")
    mission_id = reservation["missions"][0]["id"]
    must(c.post(f"/v1/missions/{mission_id}/scan-confirm", json={"barcode":"620640001001"}), "barcode verify")
    package = must(c.post(f"/v1/orders/{order['order_id']}/pack"), "create package")
    package_id = package["package_id"]
    must(c.post(f"/v1/packages/{package_id}/weight", json={"weight_g":420}), "weigh")
    must(c.post(f"/v1/packages/{package_id}/label-verify", json={"expected_label_code":"DEMO-TRACK-001","scanned_label_code":"DEMO-TRACK-001"}), "label verify")
    must(c.post(f"/v1/packages/{package_id}/assign-bay", json={"bay_id":"BAY-CP"}), "load bay")
    now = datetime.now(timezone.utc)
    pickup = must(c.post("/v1/pickups", json={"carrier":"Canada Post","bay_id":"BAY-CP","window_start":(now-timedelta(minutes=1)).isoformat(),"window_end":(now+timedelta(hours=1)).isoformat()}), "schedule pickup")
    must(c.post("/courier/access/verify", json={"pickup_id":pickup["pickup_id"],"pin":pickup["pin"]}), "courier authorize")
    headers = {"x-edge-token": "dev-edge-token"}
    commands = must(c.get("/edge/commands", headers=headers), "edge commands")["commands"]
    unlock = next(x for x in commands if x["event_type"] == "UNLOCK_BAY")
    for event_type in ["LOCKER_UNLOCKED", "OUTER_DOOR_OPENED", "OUTER_DOOR_CLOSED", "LOCKER_LOCKED"]:
        must(c.post("/edge/events", headers=headers, json={
            "command_id": unlock["id"] if event_type == "LOCKER_UNLOCKED" else None,
            "device_id": "LOCKER-PLC-01", "event_type": event_type, "payload": {"bay_id":"BAY-CP"},
        }), event_type.lower())
    must(c.post("/v1/bays/BAY-CP/handoff"), "handoff")
    must(c.get("/v1/dashboard"), "dashboard")
    print(f"\nDemo DB: {db_path}")


if __name__ == "__main__":
    main()
