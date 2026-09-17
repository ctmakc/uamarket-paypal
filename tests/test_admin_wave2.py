"""Wave 2: the owner's admin API — catalogue CRUD, photos, stock, import, activation, order queue."""
from __future__ import annotations

import csv
import io
import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, select

from app.main import create_app
from app.models import ExceptionRecord, InventoryEvent, Order, Variant
from app.services import mailer
from app.services.catalog_admin import ean13_check_digit
from app.services.ratelimit import lookup_limiter, order_limiter

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "docs" / "catalogue-import-template.csv"


@pytest.fixture()
def client(monkeypatch, tmp_path):
    for key in ("SHOP_CATALOGUE_STATUS", "PAYMENT_PROVIDER", "ETRANSFER_EMAIL", "STRIPE_SECRET_KEY", "WEB_INDEXABLE",
                "EASYPOST_API_KEY", "SHIP_FROM_ADDRESS_JSON", "MEDIA_MAX_UPLOAD_MB"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path / "media"))
    monkeypatch.setenv("WEB_BASE_URL", "http://localhost:3000")
    order_limiter.reset()
    lookup_limiter.reset()
    return TestClient(create_app(f"sqlite:///{tmp_path / f'w2-{uuid.uuid4().hex[:6]}.db'}", create_schema=True))


def jpeg(width=900, height=1200, *, exif=True) -> bytes:
    img = Image.new("RGB", (width, height), (161, 29, 43))
    out = io.BytesIO()
    kwargs = {}
    if exif:
        e = Image.Exif()
        e[0x010F] = "SecretCam"        # Make
        e[0x0131] = "firmware 1.0"     # Software
        kwargs["exif"] = e.tobytes()
    img.save(out, "JPEG", **kwargs)
    return out.getvalue()


def make_product(client, **extra) -> dict:
    maker = client.post("/v1/admin/makers", json={"name": "Test Workshop", "name_uk": "Тестова майстерня", "region": "Lviv"})
    assert maker.status_code == 201, maker.text
    body = {"title": "Linen towel", "title_uk": "Лляний рушник", "description": "A towel.", "description_uk": "Рушник.",
            "category": "home", "collection": "home", "origin": "MADE_UA", "maker_id": maker.json()["id"], **extra}
    r = client.post("/v1/admin/products", json=body)
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------------------------ makers and products

def test_maker_crud_retire_and_slug_clash(client):
    r = client.post("/v1/admin/makers", json={"name": "Kosiv Thread", "name_uk": "Косівська нитка", "founded_year": 2009})
    assert r.status_code == 201 and r.json()["slug"] == "kosiv-thread"
    mid = r.json()["id"]
    assert client.post("/v1/admin/makers", json={"name": "Kosiv thread"}).status_code == 409
    assert client.patch(f"/v1/admin/makers/{mid}", json={"region_uk": "Косів"}).json()["region_uk"] == "Косів"
    assert client.post("/v1/admin/makers", json={"name": ""}).status_code == 400
    assert client.post(f"/v1/admin/makers/{mid}/retire").json()["active"] is False
    assert [m["slug"] for m in client.get("/v1/admin/makers", params={"status": "retired"}).json()["items"]] == ["kosiv-thread"]
    assert client.post(f"/v1/admin/makers/{mid}/unretire").json()["active"] is True


def test_ukrainian_title_gets_a_latin_slug(client):
    p = make_product(client, title="Рушник весільний")
    assert p["slug"] == "rushnyk-vesilnyi"


def test_product_variants_auto_sku_barcode_and_retire(client):
    p = make_product(client)
    r = client.post(f"/v1/admin/products/{p['id']}/variants",
                    json={"option_label": "40×140 cm", "option_label_uk": "40×140 см", "price_cad": "59.9", "weight_g": 260})
    assert r.status_code == 201, r.text
    v = r.json()["variants"][0]
    assert v["sku"] == "LINEN-TOWEL-01" and v["price_cad"] == 59.9
    assert len(v["barcode"]) == 13 and v["barcode"][0] == "2" and v["barcode"][-1] == ean13_check_digit(v["barcode"][:12])
    r2 = client.post(f"/v1/admin/products/{p['id']}/variants", json={"option_label": "Big", "price_cad": 79, "weight_g": 300, "barcode": v["barcode"]})
    assert r2.status_code == 409  # the barcode belongs to the first variant
    assert client.post(f"/v1/admin/products/{p['id']}/variants", json={"sku": "bad sku!", "price_cad": 1}).status_code == 400
    retired = client.post(f"/v1/admin/variants/{v['id']}/retire").json()
    assert retired["variant_count"] == 0
    assert client.post(f"/v1/admin/variants/{v['id']}/unretire").json()["variant_count"] == 1


def test_activation_in_placeholder_mode_needs_price_and_weight(client):
    p = make_product(client)
    r = client.post(f"/v1/admin/products/{p['id']}/activate")
    assert r.status_code == 422 and {x["code"] for x in r.json()["detail"]["details"]["problems"]} == {"variants"}
    v = client.post(f"/v1/admin/products/{p['id']}/variants", json={"option_label": "One", "price_cad": 0}).json()["variants"][0]
    codes = {x["code"] for x in client.post(f"/v1/admin/products/{p['id']}/activate").json()["detail"]["details"]["problems"]}
    assert codes == {"price", "weight"}
    client.patch(f"/v1/admin/variants/{v['id']}", json={"price_cad": 25, "weight_g": 100})
    done = client.post(f"/v1/admin/products/{p['id']}/activate")
    assert done.status_code == 200 and done.json()["active"] is True
    shop = client.get("/v1/catalog/products").json()["items"]
    assert [i["slug"] for i in shop] == ["linen-towel"]


def test_activation_in_live_mode_needs_photo_alt_stock_and_size_chart(client, monkeypatch):
    monkeypatch.setenv("SHOP_CATALOGUE_STATUS", "live")
    p = make_product(client, category="women", collection="everyday")
    v = client.post(f"/v1/admin/products/{p['id']}/variants",
                    json={"option_label": "M", "option_label_uk": "M", "price_cad": 120, "weight_g": 380}).json()["variants"][0]
    codes = {x["code"] for x in client.post(f"/v1/admin/products/{p['id']}/activate").json()["detail"]["details"]["problems"]}
    assert codes == {"photo", "stock", "size_chart"}

    img = client.post(f"/v1/admin/products/{p['id']}/images", files={"file": ("a.jpg", jpeg(), "image/jpeg")}, data={"alt_en": "Towel"})
    assert img.status_code == 201, img.text
    assert client.post("/v1/admin/stock/receive", json={"sku": v["sku"], "qty": 2}).status_code == 200
    codes = {x["code"] for x in client.post(f"/v1/admin/products/{p['id']}/activate").json()["detail"]["details"]["problems"]}
    assert codes == {"alt", "size_chart"}

    client.patch(f"/v1/admin/images/{img.json()['id']}", json={"alt_uk": "Рушник"})
    # The shop-wide default chart satisfies a garment with no chart of its own.
    assert client.put("/v1/admin/settings/size-chart-default", json={"chart": {"unit": "cm", "rows": {"M": {"Chest": "96"}}}}).status_code == 200
    done = client.post(f"/v1/admin/products/{p['id']}/activate")
    assert done.status_code == 200, done.text
    page = client.get(f"/v1/catalog/products/{p['slug']}").json()
    assert page["attributes"]["size_M_chest"] == "96"
    assert page["variants"][0]["label_uk"] == "M"


# ------------------------------------------------------------------ photos

def test_upload_limits_and_derivatives(client, tmp_path):
    p = make_product(client)
    big = b"\xff\xd8" + b"0" * (30 * 1024 * 1024)
    r = client.post(f"/v1/admin/products/{p['id']}/images", files={"file": ("huge.jpg", big, "image/jpeg")})
    assert r.status_code == 413 and "limit is 15 MB" in r.json()["detail"]["message"]
    for name, body, ctype in (("x.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>", "image/svg+xml"),
                              ("x.html", b"<html><script>alert(1)</script></html>", "text/html"),
                              ("fake.jpg", b"<html>not an image</html>", "image/jpeg")):
        r = client.post(f"/v1/admin/products/{p['id']}/images", files={"file": (name, body, ctype)})
        assert r.status_code in (415, 422), (name, r.status_code)
        assert r.json()["detail"]["message"]
    r = client.post(f"/v1/admin/products/{p['id']}/images", files={"file": ("tiny.png", _png(50, 50), "image/png")})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "too_small"

    ids = []
    for i in range(3):
        r = client.post(f"/v1/admin/products/{p['id']}/images", files={"file": (f"p{i}.jpg", jpeg(2000, 1500), "image/jpeg")},
                        data={"alt_en": f"Photo {i}", "alt_uk": f"Фото {i}"})
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    first = r.json()
    assert "480w" in first["srcset"] and "1600w" in first["srcset"]
    served = client.get(first["src"])
    assert served.status_code == 200 and served.headers["content-type"] == "image/webp"
    assert "immutable" in served.headers["cache-control"]
    with Image.open(io.BytesIO(served.content)) as im:
        assert im.format == "WEBP" and im.width == 960 and not im.getexif()
    assert not list((tmp_path / "media").rglob("*.jpg"))  # the original is not kept
    assert client.get("/media/../../etc/passwd").status_code == 404

    order = client.post(f"/v1/admin/products/{p['id']}/images/order", json={"ids": list(reversed(ids))})
    assert [i["id"] for i in order.json()["images"]] == list(reversed(ids))
    assert client.post(f"/v1/admin/products/{p['id']}/images/order", json={"ids": ids[:2]}).status_code == 400
    assert client.delete(f"/v1/admin/images/{ids[0]}").json()["ok"] is True
    assert client.get(f"/v1/admin/products/{p['id']}").json()["photo_count"] == 2


def _png(w, h) -> bytes:
    out = io.BytesIO()
    Image.new("RGBA", (w, h), (0, 0, 0, 0)).save(out, "PNG")
    return out.getvalue()


# ------------------------------------------------------------------ stock

def test_receive_and_reasoned_adjustment_are_ledger_entries(client):
    p = make_product(client)
    v = client.post(f"/v1/admin/products/{p['id']}/variants", json={"option_label": "One", "price_cad": 10, "weight_g": 50}).json()["variants"][0]
    r = client.post("/v1/admin/stock/receive", json={"sku": v["sku"], "qty": 5, "note": "first box"})
    assert r.status_code == 200 and r.json()["on_hand"] == 5
    assert client.post("/v1/admin/stock/adjust", json={"sku": v["sku"], "delta": -1, "reason": "WHIM"}).status_code == 400
    r = client.post("/v1/admin/stock/adjust", json={"sku": v["sku"], "delta": -2, "reason": "DAMAGED", "note": "wet"})
    assert r.status_code == 200 and r.json()["on_hand"] == 3
    assert client.post("/v1/admin/stock/adjust", json={"sku": v["sku"], "delta": -4, "reason": "LOST"}).status_code == 409
    events = client.get(f"/v1/admin/stock/{v['sku']}/ledger").json()["events"]
    assert [(e["type"], e["qty"], e["note"]) for e in events] == [("ADJUSTMENT", -2, "wet"), ("RECEIVED", 5, "first box")]
    # The projection rebuilt from the ledger agrees.
    assert client.post("/admin/rebuild-balances").status_code == 200
    row = next(i for i in client.get("/v1/admin/stock", params={"q": v["sku"]}).json()["items"])
    assert row["on_hand"] == 3 and row["product_title"] == "Linen towel"


# ------------------------------------------------------------------ import

def test_template_import_dry_run_apply_and_update_without_duplicates(client):
    text = TEMPLATE.read_text(encoding="utf-8")
    rows = list(csv.DictReader(io.StringIO(text)))
    dry = client.post("/v1/admin/import", content=text.encode()).json()
    assert dry["errors"] == 0, dry["lines"]
    assert dry["variants"]["create"] == len(rows) and dry["applied"] is False
    assert client.get("/v1/admin/products").json()["total"] == 0  # nothing written

    applied = client.post("/v1/admin/import", params={"apply": "true"}, content=text.encode()).json()
    assert applied["applied"] is True and applied["products"]["create"] == dry["products"]["create"]
    total = client.get("/v1/admin/products").json()["total"]
    assert total == dry["products"]["create"]

    changed = text.replace(rows[0]["price_cad"], "999.00", 1)
    again = client.post("/v1/admin/import", params={"apply": "true"}, content=changed.encode()).json()
    assert again["applied"] and again["products"]["create"] == 0 and again["variants"]["create"] == 0
    assert again["variants"]["update"] == len(rows)
    assert client.get("/v1/admin/products").json()["total"] == total
    with client.app.state.SessionLocal() as db:
        assert db.scalar(select(Variant).where(Variant.sku == rows[0]["sku"])).price_cad == 999.0
        assert len(list(db.scalars(select(Variant)))) == len(rows)


def test_import_with_a_bad_row_writes_nothing(client):
    text = TEMPLATE.read_text(encoding="utf-8")
    lines = text.splitlines()
    bad = lines[1].replace(",home,", ",nosuchcategory,", 1) if ",home," in lines[1] else lines[1]
    rows = list(csv.DictReader(io.StringIO(text)))
    broken = "\n".join([lines[0], lines[1], bad.replace(rows[0]["sku"], rows[0]["sku"] + "-X").replace(rows[0]["category"], "nosuchcategory")]) + "\n"
    report = client.post("/v1/admin/import", params={"apply": "true"}, content=broken.encode()).json()
    assert report["errors"] == 1 and report["applied"] is False
    assert report["lines"][1]["status"] == "error" and "category" in report["lines"][1]["messages"][0].lower()
    assert client.get("/v1/admin/products").json()["total"] == 0
    missing = client.post("/v1/admin/import", content=b"sku,price_cad\nA,1\n").json()
    assert missing["errors"] == 1 and "product_slug" in missing["columns_missing"]


def test_seed_stays_insert_only(client):
    assert client.post("/admin/seed-catalog", params={"with_stock": "false"}).status_code == 200
    product = client.get("/v1/admin/products", params={"q": "opishnia mug"}).json()["items"][0]
    client.patch(f"/v1/admin/products/{product['id']}", json={"title": "Owner's mug"})
    assert client.post("/admin/seed-catalog", params={"with_stock": "false"}).status_code == 200
    assert client.get(f"/v1/admin/products/{product['id']}").json()["title"] == "Owner's mug"


# ------------------------------------------------------------------ orders

def _placed_paid_order(client, monkeypatch) -> dict:
    monkeypatch.setenv("PAYMENT_PROVIDER", "fake")
    monkeypatch.setattr(mailer, "TRANSPORT", lambda config, message: None)
    assert client.post("/admin/seed-catalog", params={"with_stock": "false"}).status_code == 200
    client.post("/v1/receipts", json={"sku": "OPISHNIA-MUG-01", "location_id": "A-LANE-01", "qty": 3, "reference_id": "T"})
    body = {"idempotency_key": f"w2-{uuid.uuid4()}", "email": "buyer@example.test", "name": "Olena Buyer",
            "fulfillment_method": "SHIP", "ship_to": {"street1": "1 Main St", "city": "Kanata", "province": "ON", "postal_code": "K2K1X1"},
            "lines": [{"sku": "OPISHNIA-MUG-01", "qty": 2}]}
    r = client.post("/v1/storefront/orders", json=body)
    assert r.status_code == 201, r.text
    session = r.json()["payment"]["checkout_url"].rsplit("/", 1)[1]
    assert client.post(f"/v1/payments/test/{session}/complete").status_code == 200
    with client.app.state.SessionLocal() as db:
        order = db.scalar(select(Order).where(Order.order_number == r.json()["order_number"]))
        return {"id": order.id, "number": order.order_number}


def test_order_queue_scan_pack_ship(client, monkeypatch):
    o = _placed_paid_order(client, monkeypatch)
    queue = client.get("/v1/admin/orders", params={"queue": "to_pack"}).json()
    assert [i["order_number"] for i in queue["items"]] == [o["number"]] and queue["counts"]["to_pack"] == 1
    detail = client.get(f"/v1/admin/orders/{o['id']}").json()
    assert detail["next"]["kind"] == "scan" and detail["lines"][0]["title"] == "Opishnia mug"

    wrong = client.post(f"/v1/admin/orders/{o['id']}/scan", json={"barcode": "0000000000000"})
    assert wrong.status_code == 409 and wrong.json()["detail"]["code"] == "wrong_barcode"
    assert client.get("/v1/admin/orders", params={"queue": "exceptions"}).json()["counts"]["exceptions"] == 1
    with client.app.state.SessionLocal() as db:
        barcode = db.scalar(select(Variant).where(Variant.sku == "OPISHNIA-MUG-01")).barcode
        assert db.scalar(select(ExceptionRecord).where(ExceptionRecord.kind == "WRONG_SKU")).state == "OPEN"
    ok = client.post(f"/v1/admin/orders/{o['id']}/scan", json={"barcode": barcode})
    assert ok.status_code == 200 and ok.json()["detail"]["next"]["kind"] == "pack"
    with client.app.state.SessionLocal() as db:
        assert db.scalar(select(ExceptionRecord).where(ExceptionRecord.kind == "WRONG_SKU")).state == "RESOLVED"

    packed = client.post(f"/v1/admin/orders/{o['id']}/pack", json={"weight_g": 900}).json()
    assert packed["next"]["kind"] == "ship" and packed["queue"] == "ready_to_ship"
    shipped = client.post(f"/v1/orders/{o['id']}/ship", json={"carrier": "Canada Post", "tracking_code": "TRACK123CA"})
    assert shipped.status_code == 200
    final = client.get(f"/v1/admin/orders/{o['id']}").json()
    assert final["queue"] == "shipped" and final["next"]["kind"] == "none" and final["shipment"]["tracking_code"] == "TRACK123CA"
    assert {m["kind"] for m in final["mail"]} >= {"placed", "paid", "handoff"}
    assert any("handoff" in e["text"] or "HANDOFF" in e["text"].upper() for e in final["timeline"])

    dash = client.get("/v1/dashboard").json()
    assert dash["gross_24h_cad"] == f"{final['total_cad']:.2f}"
    inv = client.get("/v1/inventory").json()["items"]
    assert any(i["product"] == "Opishnia mug" for i in inv)


def test_scan_accepts_the_sku_and_a_line_can_be_confirmed_by_hand(client, monkeypatch):
    o = _placed_paid_order(client, monkeypatch)
    detail = client.get(f"/v1/admin/orders/{o['id']}").json()
    line = detail["lines"][0]
    with client.app.state.SessionLocal() as db:
        assert line["barcode"] == db.scalar(select(Variant).where(Variant.sku == "OPISHNIA-MUG-01")).barcode

    typed = client.post(f"/v1/admin/orders/{o['id']}/scan", json={"barcode": " opishnia-mug-01 "})
    assert typed.status_code == 200, typed.text
    assert typed.json()["sku"] == "OPISHNIA-MUG-01"
    with client.app.state.SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ExceptionRecord).where(ExceptionRecord.kind == "WRONG_SKU")) == 0
    assert typed.json()["detail"]["next"]["kind"] == "pack"

    second = _placed_paid_order(client, monkeypatch)
    assert client.post(f"/v1/admin/orders/{second['id']}/lines/{line['id']}/confirm").status_code == 404
    other_line = client.get(f"/v1/admin/orders/{second['id']}").json()["lines"][0]
    by_hand = client.post(f"/v1/admin/orders/{second['id']}/lines/{other_line['id']}/confirm")
    assert by_hand.status_code == 200, by_hand.text
    body = by_hand.json()
    assert body["next"]["kind"] == "pack" and body["lines"][0]["picked"] is True
    assert any(t["kind"] == "note" and "by hand" in t["text"] and t.get("note_kind") == "HAND_CHECK" and t.get("author") for t in body["timeline"])


def test_unpaid_orders_do_not_count_as_gross_and_cancel_paid_asks_for_refund(client, monkeypatch):
    o = _placed_paid_order(client, monkeypatch)
    body = {"idempotency_key": f"w2-{uuid.uuid4()}", "email": "second@example.test", "name": "Second Buyer",
            "fulfillment_method": "SHIP", "ship_to": {"street1": "1 Main St", "city": "Kanata", "province": "ON", "postal_code": "K2K1X1"},
            "lines": [{"sku": "OPISHNIA-MUG-01", "qty": 1}]}
    unpaid = client.post("/v1/storefront/orders", json=body).json()
    gross = float(client.get("/v1/dashboard").json()["gross_24h_cad"])
    paid_total = client.get(f"/v1/admin/orders/{o['id']}").json()["total_cad"]
    assert gross == paid_total and client.get("/v1/admin/orders", params={"queue": "awaiting_payment"}).json()["counts"]["awaiting_payment"] == 1
    assert unpaid["order_number"]

    assert client.post(f"/v1/admin/orders/{o['id']}/cancel", json={"note": ""}).status_code == 422
    cancelled = client.post(f"/v1/admin/orders/{o['id']}/cancel", json={"note": "Buyer asked to cancel by phone"}).json()
    assert cancelled["state"] == "CANCELLED"
    assert any(e["kind"] == "REFUND_DUE" and e["state"] == "OPEN" for e in cancelled["exceptions"])
    assert any(t["kind"] == "note" and "phone" in t["text"] for t in cancelled["timeline"])
    stock = next(i for i in client.get("/v1/admin/stock", params={"q": "OPISHNIA-MUG-01"}).json()["items"])
    assert stock["reserved"] == 1  # only the unpaid order's hold is left


def test_admin_routes_need_the_admin_key(monkeypatch, tmp_path):
    monkeypatch.setenv("ALLOW_INSECURE_DEV", "false")
    monkeypatch.setenv("OPERATOR_API_KEY", "op-key")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-key")
    c = TestClient(create_app(f"sqlite:///{tmp_path / 'sec.db'}", create_schema=True))
    assert c.get("/v1/admin/products").status_code == 401
    assert c.get("/v1/admin/products", headers={"x-api-key": "op-key"}).status_code == 401
    assert c.get("/v1/admin/products", headers={"x-api-key": "admin-key"}).status_code == 200
    assert c.get("/v1/admin/orders", headers={"x-api-key": "op-key"}).status_code == 200
    assert c.get("/v1/admin/orders").status_code == 401
    assert c.get("/media/products/x/y-480.webp").status_code == 404


def test_web_copy_of_the_import_template_matches_docs():
    source = (ROOT / "web" / "lib" / "admin" / "template.ts").read_text(encoding="utf-8")
    embedded = json.loads(source.split("export const TEMPLATE_CSV = ", 1)[1].rstrip().rstrip(";"))
    assert embedded == TEMPLATE.read_text(encoding="utf-8")
