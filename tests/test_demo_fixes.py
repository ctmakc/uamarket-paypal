"""Fixes before the public demo (17.09.2026): photo order, cancel email, admin history codes, locker overview."""
from __future__ import annotations

from sqlalchemy import select

from app.models import OutboxMessage
from app.services.storefront import mail_key

from tests.test_admin_wave2 import _placed_paid_order, client, jpeg, make_product  # noqa: F401  (fixture)


def test_uploaded_photos_keep_their_order(client):
    p = make_product(client)
    ids = []
    for i in range(3):
        r = client.post(f"/v1/admin/products/{p['id']}/images", files={"file": (f"p{i}.jpg", jpeg(1200, 900, exif=False), "image/jpeg")})
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    images = client.get(f"/v1/admin/products/{p['id']}").json()["images"]
    assert [i["id"] for i in images] == ids
    assert [i["position"] for i in images] == [0, 1, 2]


def test_cancel_writes_to_the_buyer_and_history_has_codes(client, monkeypatch):
    o = _placed_paid_order(client, monkeypatch)
    cancelled = client.post(f"/v1/admin/orders/{o['id']}/cancel", json={"note": "Buyer asked by phone"}).json()
    assert cancelled["state"] == "CANCELLED"
    with client.app.state.SessionLocal() as db:
        row = db.scalar(select(OutboxMessage).where(OutboxMessage.idempotency_key == mail_key(o["id"], "cancelled")))
        assert row is not None and row.state in {"DELIVERED", "SKIPPED"}
    assert any(m["kind"] == "cancelled" for m in cancelled["mail"])
    preview = client.get(f"/v1/orders/{o['id']}/mail/cancelled/preview", params={"format": "text"})
    assert preview.status_code == 200, preview.text
    text = preview.text
    assert "cancelled" in text and "returned the way it was made" in text and "phone" not in text
    codes = {t.get("code") for t in cancelled["timeline"]}
    assert {"placed", "paid", "cancel"} <= codes
    assert all("params" in t for t in cancelled["timeline"])


def test_locker_overview_lists_bays_without_codes(client, monkeypatch):
    _placed_paid_order(client, monkeypatch)
    r = client.get("/v1/admin/lockers")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"pickup_configured", "bays", "devices"}
    assert "code" not in r.text.replace("customer_codes", "")


def test_mailpit_behind_public_address_promises_no_email(monkeypatch):
    from app.services import storefront as sf
    monkeypatch.setenv("SMTP_HOST", "mailpit")
    monkeypatch.setenv("MAIL_FROM", "UA Market <shop@uamarket.local>")
    monkeypatch.setenv("WEB_BASE_URL", "http://localhost:3000")
    assert sf.notifications_config()["email"] is True
    monkeypatch.setenv("WEB_BASE_URL", "https://market.agintent.com")
    assert sf.notifications_config() == {"email": False, "from_email": None}
