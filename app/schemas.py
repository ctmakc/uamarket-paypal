from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class ReceiptIn(BaseModel):
    sku: str
    location_id: str
    qty: int = Field(gt=0)
    reference_id: str


class OrderLineIn(BaseModel):
    sku: str
    qty: int = Field(gt=0)
    unit_price_cad: float = Field(ge=0)


class OrderWebhookIn(BaseModel):
    source: str
    event_id: str
    channel: str
    external_order_id: str
    lines: list[OrderLineIn]


class ScanConfirmIn(BaseModel):
    barcode: str


class WeightIn(BaseModel):
    weight_g: int = Field(gt=0)


class LabelVerifyIn(BaseModel):
    expected_label_code: str
    scanned_label_code: str


class AssignBayIn(BaseModel):
    bay_id: str


class PickupIn(BaseModel):
    carrier: str
    bay_id: str
    window_start: datetime
    window_end: datetime


class AccessVerifyIn(BaseModel):
    pickup_id: str
    pin: str


class BayStateIn(BaseModel):
    inner_gate_closed: bool | None = None
    outer_door_closed: bool | None = None
    weight_g: int | None = None


class DeviceEventIn(BaseModel):
    event_type: str
    payload: dict = Field(default_factory=dict)

class EdgeAckIn(BaseModel):
    ok: bool = True
    details: dict = Field(default_factory=dict)


class EdgeEventIn(BaseModel):
    command_id: str | None = None
    device_id: str
    event_type: str
    payload: dict = Field(default_factory=dict)

class AddressIn(BaseModel):
    name: str | None = None
    company: str | None = None
    street1: str
    street2: str | None = None
    city: str
    state: str
    zip: str
    country: str = "CA"
    phone: str | None = None
    email: str | None = None


class ShipmentQuoteIn(BaseModel):
    to_address: AddressIn
    from_address: AddressIn
    length_in: float = Field(gt=0)
    width_in: float = Field(gt=0)
    height_in: float = Field(gt=0)


class ShipmentBuyIn(BaseModel):
    rate_id: str


class PickupScheduleEasyPostIn(BaseModel):
    package_id: str
    address: AddressIn
    carrier_accounts: list[str] = Field(min_length=1)
    instructions: str = "Use exterior courier locker and access PIN from pickup instructions."


class PickupBuyEasyPostIn(BaseModel):
    carrier: str
    service: str


class CommissioningUnlockIn(BaseModel):
    site: str = "default"
    ttl_seconds: int = Field(default=5, ge=1, le=10)
    confirm: str


# --------------------------------------------------------------------- storefront (public web channel)

class WebOrderLineIn(BaseModel):
    sku: str = Field(min_length=1, max_length=80)
    qty: int = Field(ge=1, le=20)


class WebShipToIn(BaseModel):
    name: str | None = None
    street1: str = ""
    street2: str | None = None
    city: str = ""
    province: str = ""
    postal_code: str = ""
    country: str = "CA"


class WebOrderIn(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=120)
    email: str = Field(max_length=200)
    name: str = Field(max_length=200)
    phone: str | None = Field(default=None, max_length=60)
    locale: str = "en"
    fulfillment_method: str  # SHIP | PICKUP
    ship_to: WebShipToIn | None = None
    payment_method: str | None = None  # STRIPE | ETRANSFER | INVOICE (defaults to first configured)
    note: str | None = Field(default=None, max_length=1000)
    lines: list[WebOrderLineIn] = Field(min_length=1, max_length=30)
    # The buyer ticked "I accept the terms of sale and the privacy notice" next to Place order.
    terms_accepted: bool | None = None


class OrderLookupIn(BaseModel):
    order_number: str = Field(min_length=4, max_length=32)
    email: str = Field(min_length=3, max_length=200)


class MarkPaidIn(BaseModel):
    reference: str | None = Field(default=None, max_length=200)
    method: str | None = Field(default=None, max_length=20)


class QuoteShipToIn(BaseModel):
    province: str | None = Field(default=None, max_length=8)


class QuoteIn(BaseModel):
    lines: list[WebOrderLineIn] = Field(default_factory=list, max_length=30)
    fulfillment_method: str = Field(default="SHIP", pattern="^(?i:ship|pickup)$")
    ship_to: QuoteShipToIn | None = None


class ShipIn(BaseModel):
    carrier: str = Field(min_length=1, max_length=80)
    tracking_code: str = Field(min_length=3, max_length=180)
