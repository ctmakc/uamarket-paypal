"""Synthetic stress run for the application layer without real carriers/hardware."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import create_app


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--orders", type=int, default=250)
    args = ap.parse_args()
    db_path = ROOT / "stress.db"
    if db_path.exists(): db_path.unlink()
    c = TestClient(create_app(f"sqlite:///{db_path}"))
    assert c.post("/admin/seed").status_code == 200
    qty = args.orders + 10
    assert c.post("/v1/receipts", json={"sku":"UA-W-BLACK-M","location_id":"A-LANE-01","qty":qty,"reference_id":"STRESS-PO"}).status_code == 200
    for i in range(args.orders):
        o = c.post("/webhooks/order", json={
            "source":"stress","event_id":f"evt-{i}","channel":"SHOPIFY","external_order_id":f"ord-{i}",
            "lines":[{"sku":"UA-W-BLACK-M","qty":1,"unit_price_cad":79.99}],
        })
        assert o.status_code == 200, o.text
        oid = o.json()["order_id"]
        r = c.post(f"/v1/orders/{oid}/reserve"); assert r.status_code == 200, r.text
        mid = r.json()["missions"][0]["id"]
        assert c.post(f"/v1/missions/{mid}/scan-confirm", json={"barcode":"620640001001"}).status_code == 200
        p = c.post(f"/v1/orders/{oid}/pack"); assert p.status_code == 200
        pid = p.json()["package_id"]
        assert c.post(f"/v1/packages/{pid}/weight", json={"weight_g":420}).status_code == 200
        code=f"STRESS-{i:06d}"
        assert c.post(f"/v1/packages/{pid}/label-verify", json={"expected_label_code":code,"scanned_label_code":code}).status_code == 200
        assert c.post(f"/v1/packages/{pid}/assign-bay", json={"bay_id":"BAY-CP"}).status_code == 200
    d = c.get("/v1/dashboard").json()
    outbox = c.get("/admin/outbox").json()["messages"]
    print({"orders": args.orders, "dashboard": d, "recent_outbox": len(outbox), "db": str(db_path)})


if __name__ == "__main__":
    main()
