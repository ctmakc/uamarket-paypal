from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, false, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def uid() -> str:
    return str(uuid.uuid4())


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# Money is stored exactly, as NUMERIC(10,2). Python reads it back as a float rounded to the
# cent (asdecimal=False): every caller already rounds to two places, and the JSON the API
# and the outbox write cannot carry a Decimal.
def Money():
    return Numeric(10, 2, asdecimal=False)


class Variant(Base):
    __tablename__ = "variants"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    sku: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(240))
    barcode: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    price_cad: Mapped[float] = mapped_column(Money(), default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Storefront catalogue link (nullable: warehouse-only SKUs stay valid without a product).
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id"), nullable=True, index=True)
    option_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    option_label_uk: Mapped[str | None] = mapped_column(String(120), nullable=True)
    option_json: Mapped[str] = mapped_column(Text, default="{}")
    weight_g: Mapped[int | None] = mapped_column(Integer, nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    # What the shop paid; never leaves the operator side.
    cost_cad: Mapped[float | None] = mapped_column(Money(), nullable=True)
    # Customs and label facts, per sellable unit.
    fibre_content: Mapped[str | None] = mapped_column(String(240), nullable=True)
    country_of_origin: Mapped[str | None] = mapped_column(String(2), nullable=True)
    hs_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Parcel dimensions of one packed unit, in centimetres.
    length_cm: Mapped[float | None] = mapped_column(Numeric(7, 1, asdecimal=False), nullable=True)
    width_cm: Mapped[float | None] = mapped_column(Numeric(7, 1, asdecimal=False), nullable=True)
    height_cm: Mapped[float | None] = mapped_column(Numeric(7, 1, asdecimal=False), nullable=True)


class Location(Base):
    __tablename__ = "locations"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class InventoryEvent(Base):
    __tablename__ = "inventory_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    variant_id: Mapped[str] = mapped_column(ForeignKey("variants.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    qty: Mapped[int] = mapped_column(Integer)
    from_location_id: Mapped[str | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    to_location_id: Mapped[str | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    reference_type: Mapped[str] = mapped_column(String(40))
    reference_id: Mapped[str] = mapped_column(String(120), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
    # Free text an operator wrote with a receipt or an adjustment ("found in the back room").
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor: Mapped[str | None] = mapped_column(String(120), nullable=True)


class InventoryBalance(Base):
    __tablename__ = "inventory_balances"
    variant_id: Mapped[str] = mapped_column(ForeignKey("variants.id"), primary_key=True)
    location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), primary_key=True)
    qty_on_hand: Mapped[int] = mapped_column(Integer, default=0)
    qty_reserved: Mapped[int] = mapped_column(Integer, default=0)

    @property
    def qty_available(self) -> int:
        return self.qty_on_hand - self.qty_reserved


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    __table_args__ = (UniqueConstraint("source", "external_event_id", name="uq_webhook_source_event"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    source: Mapped[str] = mapped_column(String(40))
    external_event_id: Mapped[str] = mapped_column(String(160))
    payload_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (UniqueConstraint("channel", "external_id", name="uq_order_channel_external"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    channel: Mapped[str] = mapped_column(String(40), index=True)
    external_id: Mapped[str] = mapped_column(String(160))
    state: Mapped[str] = mapped_column(String(40), default="PAID", index=True)
    gross_amount_cad: Mapped[float] = mapped_column(Money(), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    # Storefront (channel WEB) fields. Nullable so Shopify/demo orders are untouched.
    order_number: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True, index=True)
    customer_email: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    customer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    customer_phone: Mapped[str | None] = mapped_column(String(60), nullable=True)
    locale: Mapped[str | None] = mapped_column(String(8), nullable=True)
    fulfillment_method: Mapped[str | None] = mapped_column(String(20), nullable=True)  # SHIP | PICKUP
    ship_to_json: Mapped[str] = mapped_column(Text, default="{}")
    subtotal_cad: Mapped[float | None] = mapped_column(Money(), nullable=True)
    shipping_cad: Mapped[float | None] = mapped_column(Money(), nullable=True)
    tax_cad: Mapped[float | None] = mapped_column(Money(), nullable=True)
    tax_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    # The named tax lines (GST, HST, QST, PST) computed at placement, as JSON.
    tax_lines_json: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    # Opaque key to the buyer's own order page (email link, cookie). Never an email address.
    access_token: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)
    payment_method: Mapped[str | None] = mapped_column(String(20), nullable=True)  # STRIPE | PAYPAL | ETRANSFER | INVOICE
    payment_ref: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    customer_note: Mapped[str] = mapped_column(Text, default="")
    # True for every order placed while SHOP_CATALOGUE_STATUS is not "live": the goods are
    # demonstration data, so the order page and the email tell the buyer to send no money.
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # The card checkout session currently open for this order (Stripe, or the local fake).
    checkout_session_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    # Placement holds stock until this moment; the sweep releases what is still unpaid.
    hold_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    # What the buyer was told when the order was placed (payment block, status), frozen so
    # a resent "order received" email repeats it instead of describing a later state.
    placement_json: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")
    # PayPal (payment_method PAYPAL): the PayPal order this shop order is paid through, the
    # capture that moved the money, PayPal's last word on it, and what the shop has pushed
    # back to PayPal since (the tracking number, a refund). Ids only; no buyer data from PayPal.
    paypal_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    paypal_capture_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    paypal_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    paypal_tracking_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    paypal_refund_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lines: Mapped[list[OrderLine]] = relationship(back_populates="order", cascade="all, delete-orphan")


class OrderLine(Base):
    __tablename__ = "order_lines"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    variant_id: Mapped[str] = mapped_column(ForeignKey("variants.id"), index=True)
    qty: Mapped[int] = mapped_column(Integer)
    unit_price_cad: Mapped[float] = mapped_column(Money())
    order: Mapped[Order] = relationship(back_populates="lines")


class Reservation(Base):
    __tablename__ = "reservations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    # Not unique: one line can be held across several sellable locations.
    order_line_id: Mapped[str] = mapped_column(ForeignKey("order_lines.id"), index=True)
    variant_id: Mapped[str] = mapped_column(ForeignKey("variants.id"), index=True)
    location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), index=True)
    qty: Mapped[int] = mapped_column(Integer)
    # HOLD (placed, unpaid, time-limited) -> ACTIVE (paid) -> CONSUMED (shipped),
    # or HOLD -> RELEASED (hold expired or order cancelled).
    state: Mapped[str] = mapped_column(String(30), default="ACTIVE")


class Mission(Base):
    __tablename__ = "missions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    order_line_id: Mapped[str] = mapped_column(ForeignKey("order_lines.id"), index=True)
    variant_id: Mapped[str] = mapped_column(ForeignKey("variants.id"), index=True)
    location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), index=True)
    qty: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(30), default="READY", index=True)
    scanned_barcode: Mapped[str | None] = mapped_column(String(120), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Bay(Base):
    __tablename__ = "bays"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    carrier_group: Mapped[str] = mapped_column(String(60), index=True)
    inner_gate_closed: Mapped[bool] = mapped_column(Boolean, default=True)
    outer_door_locked: Mapped[bool] = mapped_column(Boolean, default=True)
    outer_door_closed: Mapped[bool] = mapped_column(Boolean, default=True)
    weight_g: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Package(Base):
    __tablename__ = "packages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), unique=True, index=True)
    state: Mapped[str] = mapped_column(String(40), default="PACKING", index=True)
    weight_g: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expected_label_code: Mapped[str | None] = mapped_column(String(180), nullable=True)
    scanned_label_code: Mapped[str | None] = mapped_column(String(180), nullable=True)
    bay_id: Mapped[str | None] = mapped_column(ForeignKey("bays.id"), nullable=True, index=True)


class ShipmentRecord(Base):
    __tablename__ = "shipments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    package_id: Mapped[str] = mapped_column(ForeignKey("packages.id"), unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(40), default="EASYPOST")
    external_shipment_id: Mapped[str | None] = mapped_column(String(120), nullable=True, unique=True)
    state: Mapped[str] = mapped_column(String(40), default="RATED", index=True)
    selected_rate_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    carrier: Mapped[str | None] = mapped_column(String(80), nullable=True)
    service: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tracking_code: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    label_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    label_zpl_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    postage_amount: Mapped[float | None] = mapped_column(Money(), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    rates_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    # Set and committed immediately before the buy call leaves for the carrier API, so a crash
    # between the request and its response is still visible on the next attempt. While it is set
    # and state is not PURCHASED, the purchase outcome is unknown and must be read back from the
    # carrier rather than bought again.
    purchase_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CourierPickup(Base):
    __tablename__ = "courier_pickups"
    __table_args__ = (Index("uq_courier_pickups_external_pickup_id", "external_pickup_id", unique=True),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    carrier: Mapped[str] = mapped_column(String(60), index=True)
    bay_id: Mapped[str] = mapped_column(ForeignKey("bays.id"), index=True)
    state: Mapped[str] = mapped_column(String(40), default="SCHEDULED", index=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    external_pickup_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    external_status: Mapped[str | None] = mapped_column(String(60), nullable=True)
    external_rates_json: Mapped[str] = mapped_column(Text, default="[]")


class LockerAccess(Base):
    """One credential that opens one bay once.

    Two kinds live in this table, and neither can be used in the other one's place:

    * ``COURIER``  — carries ``pickup_id`` and no ``order_id``. It belongs to a scheduled
      CourierPickup, its window is that pickup's window, and it is what the carrier types
      at the door to collect everything the bay holds.
    * ``CUSTOMER`` — carries ``order_id`` and no ``pickup_id``. It belongs to one web order
      that was bought for locker pickup, it opens the single bay that order's parcel was
      assigned to, its window starts when the parcel goes in, and it is revoked the moment
      the parcel leaves the bay.

    The two verification paths query on ``kind`` as well as on the owning row, so a customer
    code can never satisfy a courier handoff and a courier PIN can never open a customer's
    bay. ``pin_hash`` is a salted PBKDF2 digest for both kinds; see app/services/locker.py.
    """
    __tablename__ = "locker_access"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    kind: Mapped[str] = mapped_column(String(20), default="COURIER", index=True)
    # Exactly one of these two is set, and which one is set is what `kind` names.
    pickup_id: Mapped[str | None] = mapped_column(ForeignKey("courier_pickups.id"), nullable=True, index=True)
    order_id: Mapped[str | None] = mapped_column(ForeignKey("orders.id"), nullable=True, index=True)
    bay_id: Mapped[str] = mapped_column(ForeignKey("bays.id"), index=True)
    pin_hash: Mapped[str] = mapped_column(String(64))
    # A customer has to be able to read their code again every time they open their order
    # page, so a CUSTOMER row also keeps the code itself here until the credential is spent
    # or revoked, and then this column is emptied. A COURIER row never fills it: a courier
    # PIN is handed to the operator once and lives only in the hash.
    display_code: Mapped[str | None] = mapped_column(String(12), nullable=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set when the parcel leaves the bay, or when the parcel is moved to another bay. A
    # revoked credential is refused at the door whatever its window says.
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(String(60), nullable=True)


class Device(Base):
    __tablename__ = "devices"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    kind: Mapped[str] = mapped_column(String(40))
    state: Mapped[str] = mapped_column(String(40), default="ONLINE")
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class DeviceEvent(Base):
    __tablename__ = "device_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(60))
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ExceptionRecord(Base):
    __tablename__ = "exceptions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    kind: Mapped[str] = mapped_column(String(60), index=True)
    reference_type: Mapped[str] = mapped_column(String(40))
    reference_id: Mapped[str] = mapped_column(String(120), index=True)
    # OPEN until an operator resolves it through POST /v1/exceptions/{id}/resolve.
    state: Mapped[str] = mapped_column(String(30), default="OPEN", index=True)
    details: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class OutboxMessage(Base):
    __tablename__ = "outbox_messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    topic: Mapped[str] = mapped_column(String(180), index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    aggregate_type: Mapped[str] = mapped_column(String(60), index=True)
    aggregate_id: Mapped[str] = mapped_column(String(120), index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    state: Mapped[str] = mapped_column(String(30), default="PENDING", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    idempotency_key: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Maker(Base):
    """Marketplace seller / workshop shown on the storefront."""
    __tablename__ = "makers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    name_uk: Mapped[str | None] = mapped_column(String(200), nullable=True)
    region: Mapped[str] = mapped_column(String(200), default="")
    region_uk: Mapped[str | None] = mapped_column(String(200), nullable=True)
    country: Mapped[str] = mapped_column(String(2), default="UA")
    craft: Mapped[str] = mapped_column(String(200), default="")
    craft_uk: Mapped[str | None] = mapped_column(String(200), nullable=True)
    story: Mapped[str] = mapped_column(Text, default="")
    story_uk: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(400), nullable=True)
    founded_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Product(Base):
    """Storefront product. Sellable units are its Variants (SKUs)."""
    __tablename__ = "products"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(240))
    title_uk: Mapped[str | None] = mapped_column(String(240), nullable=True)
    subtitle: Mapped[str | None] = mapped_column(String(240), nullable=True)
    subtitle_uk: Mapped[str | None] = mapped_column(String(240), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    description_uk: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(60), index=True)
    collection: Mapped[str] = mapped_column(String(60), index=True)
    maker_id: Mapped[str | None] = mapped_column(ForeignKey("makers.id"), nullable=True, index=True)
    # HANDMADE_UA = hand-made in Ukraine · MADE_UA = made in Ukraine (workshop/machine) · DESIGNED_UA = designed in Ukraine, made abroad
    origin: Mapped[str] = mapped_column(String(20), default="MADE_UA", index=True)
    origin_note: Mapped[str | None] = mapped_column(String(240), nullable=True)
    origin_note_uk: Mapped[str | None] = mapped_column(String(240), nullable=True)
    technique: Mapped[str | None] = mapped_column(String(240), nullable=True)
    technique_uk: Mapped[str | None] = mapped_column(String(240), nullable=True)
    material: Mapped[str | None] = mapped_column(String(240), nullable=True)
    material_uk: Mapped[str | None] = mapped_column(String(240), nullable=True)
    care: Mapped[str | None] = mapped_column(String(400), nullable=True)
    care_uk: Mapped[str | None] = mapped_column(String(400), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(400), nullable=True)
    images_json: Mapped[str] = mapped_column(Text, default="[]")
    attributes_json: Mapped[str] = mapped_column(Text, default="{}")
    # {"unit": "cm"|"in", "note": str, "note_uk": str, "rows": {"S": {"chest": "96", ...}}}.
    # Null falls back to the shop-wide default (ShopSetting "size_chart_default").
    size_chart_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    featured: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ProductImage(Base):
    """One uploaded photo. Files live under MEDIA_ROOT/products/<product id>/<image id>-<width>.webp."""
    __tablename__ = "product_images"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    alt_en: Mapped[str] = mapped_column(String(300), default="")
    alt_uk: Mapped[str] = mapped_column(String(300), default="")
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    # Widths of the derivatives written for this image, e.g. "480,960,1600".
    widths: Mapped[str] = mapped_column(String(60))
    original_name: Mapped[str] = mapped_column(String(200), default="")
    bytes_in: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Category(Base):
    __tablename__ = "categories"
    slug: Mapped[str] = mapped_column(String(60), primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    title_uk: Mapped[str] = mapped_column(String(120))
    # Garments need a size chart before they may be sold on the live catalogue.
    garment: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    position: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())


class Collection(Base):
    __tablename__ = "collections"
    slug: Mapped[str] = mapped_column(String(60), primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    title_uk: Mapped[str] = mapped_column(String(120))
    lede: Mapped[str] = mapped_column(Text, default="")
    lede_uk: Mapped[str] = mapped_column(Text, default="")
    position: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())


class ShopSetting(Base):
    """Small owner-editable values that are data rather than deployment config."""
    __tablename__ = "shop_settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text, default="null")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class OrderNote(Base):
    """What an operator wrote on an order: a cancellation reason, a refund made, a call."""
    __tablename__ = "order_notes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40), default="NOTE")
    body: Mapped[str] = mapped_column(Text)
    author: Mapped[str] = mapped_column(String(120), default="operator")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
