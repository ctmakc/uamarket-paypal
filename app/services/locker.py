from __future__ import annotations

import base64
import binascii
import hashlib
import json
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Bay, CourierPickup, LockerAccess, Order
from .outbox import enqueue


class LockerError(RuntimeError):
    pass


# ------------------------------------------------------------------ PIN storage
#
# A courier PIN is 6 digits: 1 000 000 combinations. A plain SHA-256 digest of that is
# reversible by exhaustive search in under a second, so anyone who reads the
# locker_access table reads every live PIN. Stored PINs therefore use PBKDF2-HMAC-SHA256
# with a per-row salt.
#
# Encoded form (fits the 64-character locker_access.pin_hash column):
#   p2$<iterations>$<salt, base64url, no padding>$<derived key, base64url, no padding>
# 12-byte salt + 24-byte key = 59 characters at the default iteration count.
#
# LOCKER_PIN_KDF_ITERATIONS overrides the work factor; default below.

_PIN_KDF_TAG = "p2"
_PIN_KDF_ITERATIONS = 200_000
_PIN_KDF_SALT_BYTES = 12
_PIN_KDF_KEY_BYTES = 24


def _iterations() -> int:
    raw = (os.getenv("LOCKER_PIN_KDF_ITERATIONS") or "").strip()
    if not raw:
        return _PIN_KDF_ITERATIONS
    try:
        value = int(raw)
    except ValueError:
        return _PIN_KDF_ITERATIONS
    return value if value >= 1000 else _PIN_KDF_ITERATIONS


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _derive(pin: str, salt: bytes, iterations: int, key_bytes: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, iterations, dklen=key_bytes)


def hash_pin(pin: str, *, iterations: int | None = None) -> str:
    iterations = iterations or _iterations()
    salt = secrets.token_bytes(_PIN_KDF_SALT_BYTES)
    key = _derive(pin, salt, iterations, _PIN_KDF_KEY_BYTES)
    return f"{_PIN_KDF_TAG}${iterations}${_b64(salt)}${_b64(key)}"


def verify_pin(pin: str, stored: str) -> bool:
    """Constant-time PIN check. Understands both the KDF form and legacy SHA-256 rows."""
    stored = stored or ""
    if stored.startswith(f"{_PIN_KDF_TAG}$"):
        parts = stored.split("$")
        if len(parts) != 4:
            return False
        try:
            iterations = int(parts[1])
            salt = _unb64(parts[2])
            expected = _unb64(parts[3])
        except (ValueError, binascii.Error):
            return False
        if iterations < 1 or not salt or not expected:
            return False
        return hmac.compare_digest(_derive(pin, salt, iterations, len(expected)), expected)
    # Rows written before the KDF migration: bare SHA-256 hex. Still verified so an
    # in-flight pickup keeps working; upgraded in place on the next successful use.
    return hmac.compare_digest(hashlib.sha256(pin.encode("utf-8")).hexdigest(), stored)


def needs_rehash(stored: str) -> bool:
    """True when a stored hash is legacy or below the current work factor."""
    stored = stored or ""
    if not stored.startswith(f"{_PIN_KDF_TAG}$"):
        return True
    parts = stored.split("$")
    if len(parts) != 4:
        return True
    try:
        return int(parts[1]) < _iterations()
    except ValueError:
        return True


# ------------------------------------------------------------------ credential kinds

COURIER = "COURIER"
CUSTOMER = "CUSTOMER"


def _aware(value: datetime) -> datetime:
    """Rows written by SQLite come back naive; every comparison here is in UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _new_pin() -> str:
    return f"{secrets.randbelow(1000000):06d}"


def _edge_target() -> tuple[str, str]:
    site = os.getenv("LOCKER_EDGE_SITE") or os.getenv("EDGE_SITE", "default")
    device_id = os.getenv("LOCKER_EDGE_DEVICE_ID") or os.getenv("EDGE_DEVICE_ID", "LOCKER-PLC-01")
    return site, device_id


def _check_bay(db: Session, access: LockerAccess) -> Bay:
    """The physical preconditions for opening a bay. Identical for both kinds of credential."""
    bay = db.get(Bay, access.bay_id)
    if not bay or not bay.enabled:
        raise LockerError("Bay unavailable")
    if not bay.inner_gate_closed:
        raise LockerError("Safety interlock: inner gate is open")
    if not bay.outer_door_closed:
        raise LockerError("Outer door already open")
    return bay


def _request_unlock(db: Session, access: LockerAccess, bay: Bay, *, now: datetime, payload: dict) -> None:
    """Ask the edge to open the bay. Cloud never claims the door moved; the edge reports it."""
    edge_site, edge_device_id = _edge_target()
    command_expires_at = min(_aware(access.valid_until), now + timedelta(seconds=120))
    enqueue(
        db,
        topic=f"edge/{edge_site}/{edge_device_id}/commands/locker/{bay.id}",
        event_type="UNLOCK_BAY",
        aggregate_type="BAY",
        aggregate_id=bay.id,
        payload={
            **payload, "bay_id": bay.id, "device_id": edge_device_id,
            "action": "UNLOCK", "ttl_seconds": 60, "expires_at": command_expires_at.isoformat(),
        },
        idempotency_key=f"unlock:{access.id}",
    )


def issue_access(db: Session, pickup: CourierPickup) -> str:
    """The courier credential: one PIN for one scheduled pickup, valid for its window."""
    pin = _new_pin()
    db.add(LockerAccess(
        kind=COURIER,
        pickup_id=pickup.id,
        order_id=None,
        bay_id=pickup.bay_id,
        pin_hash=hash_pin(pin),
        display_code=None,
        valid_from=pickup.window_start,
        valid_until=pickup.window_end,
    ))
    return pin


def verify_and_open(db: Session, pickup_id: str, pin: str, now: datetime | None = None) -> Bay:
    now = now or datetime.now(timezone.utc)
    access = db.scalar(
        select(LockerAccess)
        .where(LockerAccess.kind == COURIER, LockerAccess.pickup_id == pickup_id)
        .order_by(LockerAccess.valid_until.desc())
    )
    if not access:
        raise LockerError("No access credential")
    if access.used_at is not None:
        raise LockerError("PIN already used")
    if access.revoked_at is not None:
        raise LockerError("PIN withdrawn")
    valid_from = _aware(access.valid_from)
    valid_until = _aware(access.valid_until)
    if not (valid_from <= now <= valid_until):
        raise LockerError("PIN outside pickup window")
    if not verify_pin(pin, access.pin_hash):
        raise LockerError("Invalid PIN")
    if needs_rehash(access.pin_hash):
        access.pin_hash = hash_pin(pin)
    bay = _check_bay(db, access)
    access.used_at = now
    pickup = db.get(CourierPickup, pickup_id)
    # Cloud authorizes an unlock request but never claims physical state changed.
    # The bay remains locked until the edge/PLC reports LOCKER_UNLOCKED.
    pickup.state = "UNLOCK_REQUESTED"
    _request_unlock(db, access, bay, now=now, payload={"pickup_id": pickup.id})
    return bay


def close_after_pickup(db: Session, bay: Bay):
    # Never fabricate physical door state in cloud software. Handoff is allowed
    # only after edge/PLC sensor events report the door closed and re-locked.
    if not bay.outer_door_closed:
        raise LockerError("Cannot complete handoff: outer door still open")
    if not bay.outer_door_locked:
        raise LockerError("Cannot complete handoff: outer door not re-locked")
    bay.weight_g = 0


# ------------------------------------------------------------------ pickup configuration
#
# The shop may offer locker pickup only when the owner has said where the locker is. There
# is no default address and there never will be one: an address is a fact about a building
# in Ottawa, and this repository does not know it.
#
#   PICKUP_ENABLED            on/off switch, default on
#   PICKUP_ADDRESS            the street address a buyer walks to. EMPTY = pickup is not
#                             offered at checkout, whatever PICKUP_ENABLED says.
#   PICKUP_HOURS              when the address can be reached, free text. Optional.
#   PICKUP_NOTE               one more line the buyer needs (lane, buzzer, parking). Optional.
#   PICKUP_CODE_VALID_HOURS   how long a customer's code opens the bay, default 72
#   PICKUP_LABEL              what the checkout calls this method
#   PICKUP_LABEL_UK           the same in Ukrainian
#   PICKUP_PROVINCE           province used for tax on a pickup order, default ON

DEFAULT_PICKUP_LABEL = "Locker pickup"
DEFAULT_PICKUP_LABEL_UK = "Самовивіз із локера"
DEFAULT_CODE_VALID_HOURS = 72
MAX_CODE_VALID_HOURS = 24 * 30


def _text(name: str) -> str | None:
    value = (os.getenv(name) or "").strip()
    return value or None


def _switch(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


# The storefront pages carry their own copy of this address in schema.org shape
# (SHOP_PICKUP_ADDRESS_JSON, read by web/lib/seo.ts) so Google can be handed a
# PostalAddress. One address, two settings, is one address too many to keep in step, so
# PICKUP_ADDRESS falls back to that JSON and the owner may fill in whichever they prefer.
_STREET_KEYS = ("streetAddress", "line1", "street1", "street")
_ADDRESS_KEYS = (
    _STREET_KEYS,
    ("addressLine2", "line2", "street2"),
    ("addressLocality", "city"),
    ("addressRegion", "province", "region", "state"),
    ("postalCode", "postal_code", "postcode"),
)


def _address_from_json(raw: str | None) -> str | None:
    """One printable line out of the structured address the storefront pages read.

    A city on its own is not somewhere a person can walk to. Without a street component
    this reads as no address at all, so the shop keeps pickup switched off rather than
    selling "collect it in Ottawa" and minting a code with nowhere to take it.
    """
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    parts: list[str] = []
    for names in _ADDRESS_KEYS:
        for name in names:
            value = str(data.get(name) or "").strip()
            if value:
                parts.append(value)
                break
    if not any(str(data.get(name) or "").strip() for name in _STREET_KEYS):
        return None
    return ", ".join(parts) or None


def pickup_address() -> str | None:
    """Where the locker is, or None while the owner has not said."""
    # The structured setting wins when it parses. It is the only shape that can also
    # produce a schema.org PostalAddress, so web/lib/seo.ts reads it for the Store node;
    # if the plain string won here instead, a shop that filled in both would print one
    # street to a reader and publish another to Google from the same response.
    return _address_from_json(os.getenv("SHOP_PICKUP_ADDRESS_JSON")) or _text("PICKUP_ADDRESS")


def pickup_hours() -> str | None:
    return _text("PICKUP_HOURS") or _text("SHOP_PICKUP_HOURS")


def pickup_note() -> str | None:
    return _text("PICKUP_NOTE")


def code_valid_hours() -> int:
    raw = (os.getenv("PICKUP_CODE_VALID_HOURS") or "").strip()
    if not raw:
        return DEFAULT_CODE_VALID_HOURS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_CODE_VALID_HOURS
    if value < 1 or value > MAX_CODE_VALID_HOURS:
        return DEFAULT_CODE_VALID_HOURS
    return value


def pickup_config() -> dict:
    """Everything the storefront may say about locker pickup.

    ``enabled`` is what the checkout reads, and it is true only when the switch is on AND
    an address exists. A shop with the switch on and no address offers no pickup at all,
    which is the honest state: the code that opens the bay would arrive with nowhere to go.
    """
    address = pickup_address()
    switch = _switch("PICKUP_ENABLED", True)
    return {
        "enabled": bool(switch and address),
        "switch_on": switch,
        "address_configured": bool(address),
        "label": os.getenv("PICKUP_LABEL", DEFAULT_PICKUP_LABEL),
        "label_uk": os.getenv("PICKUP_LABEL_UK", DEFAULT_PICKUP_LABEL_UK),
        "province": os.getenv("PICKUP_PROVINCE", "ON").upper(),
        "address": address,
        "hours": pickup_hours(),
        "note": pickup_note(),
        "code_valid_hours": code_valid_hours(),
    }


# ------------------------------------------------------------------ customer credential
#
# What a CUSTOMER credential is, and how it differs from the COURIER one above:
#
#   belongs to        one Order (order_id), never a CourierPickup
#   opens             the one bay that order's parcel was assigned to
#   window            starts when the parcel goes into the bay, lasts PICKUP_CODE_VALID_HOURS
#   readable again    yes — the buyer's own order page prints it until it is spent, so the
#                     code is kept in `display_code` beside the PBKDF2 hash. The hash is
#                     still the only thing the door check reads. What the pair costs and
#                     what it does not: a reader of this database can already take
#                     orders.order_number and orders.customer_email, which is the whole of
#                     the proof the public status endpoint asks for, and read the code from
#                     the shop's own API. The stored copy therefore hands a database reader
#                     nothing they could not already fetch, and it is erased the moment the
#                     credential is used or revoked.
#   revoked           when the parcel leaves the bay (handoff), or when the parcel is moved
#                     to a different bay. A revoked credential is refused at the door.
#   never             satisfies a courier handoff: /courier/access/verify reads COURIER rows
#                     only, /pickup/access/verify reads CUSTOMER rows only.


def latest_customer_access(db: Session, order_id: str) -> LockerAccess | None:
    """The newest customer credential ever minted for this order, spent or not."""
    return db.scalar(
        select(LockerAccess)
        .where(LockerAccess.kind == CUSTOMER, LockerAccess.order_id == order_id)
        .order_by(LockerAccess.valid_until.desc())
    )


def live_customer_access(db: Session, order_id: str, now: datetime | None = None) -> LockerAccess | None:
    """The credential this order can open a bay with right now, or None."""
    now = now or datetime.now(timezone.utc)
    rows = db.scalars(
        select(LockerAccess)
        .where(
            LockerAccess.kind == CUSTOMER,
            LockerAccess.order_id == order_id,
            LockerAccess.used_at.is_(None),
            LockerAccess.revoked_at.is_(None),
        )
        .order_by(LockerAccess.valid_until.desc())
    )
    for access in rows:
        if _aware(access.valid_from) <= now <= _aware(access.valid_until):
            return access
    return None


def forget_expired_display_codes(
    db: Session, *, order_id: str, now: datetime | None = None,
) -> list[LockerAccess]:
    """Erase the readable digits of credentials whose last hour has passed.

    A code is kept in readable form so the buyer's own page can print it back to them, and
    the two ends of that deal are already handled: a spent code is erased when it is spent
    and a withdrawn one when it is withdrawn. A credential that simply ran out of hours had
    nothing erasing it, so the digits sat in the row for as long as the order did. They
    open nothing, and the row keeps its hash, which is the record that a credential existed.
    """
    now = now or datetime.now(timezone.utc)
    rows = [
        access for access in db.scalars(
            select(LockerAccess).where(
                LockerAccess.kind == CUSTOMER,
                LockerAccess.order_id == order_id,
                LockerAccess.display_code.is_not(None),
            )
        )
        if _aware(access.valid_until) < now
    ]
    for access in rows:
        access.display_code = None
    return rows


def revoke_customer_access(
    db: Session, *, order_id: str | None = None, bay_id: str | None = None,
    reason: str = "", now: datetime | None = None, unspent_only: bool = False,
) -> list[LockerAccess]:
    """Withdraw customer credentials and erase the codes they carried.

    One of ``order_id`` or ``bay_id`` is required, so this can never empty the table.

    ``unspent_only`` leaves alone the credentials that were already spent at the door. A
    spent one opens nothing either way, and it is the record that somebody stood at that
    bay and it opened for them — which is what lets an operator complete the handoff. The
    operator minting a replacement code wants the unspent ones withdrawn and that record
    kept; emptying the bay wants everything withdrawn, so that caller leaves this off.
    """
    if not order_id and not bay_id:
        raise LockerError("revoke_customer_access needs an order or a bay")
    now = now or datetime.now(timezone.utc)
    stmt = select(LockerAccess).where(
        LockerAccess.kind == CUSTOMER, LockerAccess.revoked_at.is_(None),
    )
    if unspent_only:
        stmt = stmt.where(LockerAccess.used_at.is_(None))
    if order_id:
        stmt = stmt.where(LockerAccess.order_id == order_id)
    if bay_id:
        stmt = stmt.where(LockerAccess.bay_id == bay_id)
    rows = list(db.scalars(stmt))
    for access in rows:
        access.revoked_at = now
        access.revoked_reason = (reason or "")[:60] or None
        access.display_code = None
    # The session runs with autoflush off, so without this the next SELECT still matches
    # the row it just withdrew: the database says revoked_at IS NULL while the object in
    # memory has already lost its digits. issue_customer_access then treated the withdrawn
    # credential as the live one and handed the operator a code of None, leaving a buyer
    # who asked for a replacement holding nothing at all.
    if rows:
        db.flush()
    return rows


def issue_customer_access(
    db: Session, *, order: Order, bay_id: str, now: datetime | None = None,
) -> LockerAccess:
    """Mint the one-time code that lets the buyer of ``order`` open ``bay_id`` once.

    Calling this twice for the same order and the same bay returns the credential that is
    already live rather than a second code, so re-assigning the same bay does not leave a
    customer holding two codes and does not send a second email.
    """
    now = now or datetime.now(timezone.utc)
    existing = live_customer_access(db, order.id, now=now)
    if existing is not None:
        # A credential whose digits are gone can never be shown to the buyer again, so
        # returning it would answer "give this buyer a code" with silence.
        if existing.bay_id == bay_id and existing.display_code:
            return existing
        revoke_customer_access(db, order_id=order.id, reason="PARCEL_MOVED_TO_ANOTHER_BAY", now=now)
    pin = _new_pin()
    access = LockerAccess(
        kind=CUSTOMER,
        pickup_id=None,
        order_id=order.id,
        bay_id=bay_id,
        pin_hash=hash_pin(pin),
        display_code=pin,
        valid_from=now,
        valid_until=now + timedelta(hours=code_valid_hours()),
    )
    db.add(access)
    db.flush()
    return access


# One derivation of a code nobody holds. Every refusal runs the key derivation exactly
# once against either the real hash or this one, so the time the door takes cannot separate
# a real order number from an invented one. Before this, an unknown order was refused in
# 2.7 ms and a real one in 50.6 ms, and the gap was a free order-number oracle.
_DUMMY_PIN_HASH = hash_pin("000000")


def burn_verify(pin: str) -> None:
    """Pay the cost of one code check without having a credential to check."""
    verify_pin(pin or "", _DUMMY_PIN_HASH)


def verify_and_open_customer(db: Session, order: Order, pin: str, now: datetime | None = None) -> Bay:
    """The buyer's side of the door. Same interlocks as the courier's, different credential."""
    now = now or datetime.now(timezone.utc)
    access = latest_customer_access(db, order.id)
    # Derived before any branch, and always exactly once.
    matches = verify_pin(pin, access.pin_hash if access else _DUMMY_PIN_HASH)
    if not access:
        raise LockerError("No access credential")
    if access.used_at is not None:
        raise LockerError("Code already used")
    if access.revoked_at is not None:
        raise LockerError("Code withdrawn")
    if not (_aware(access.valid_from) <= now <= _aware(access.valid_until)):
        raise LockerError("Code outside its validity window")
    if not matches:
        raise LockerError("Invalid code")
    if needs_rehash(access.pin_hash):
        access.pin_hash = hash_pin(pin)
    bay = _check_bay(db, access)
    # Spent: one open per code, and the code stops being readable on the order page.
    access.used_at = now
    access.display_code = None
    _request_unlock(db, access, bay, now=now,
                    payload={"order_id": order.id, "order_number": order.order_number})
    return bay


def sweep_expired_pickup_codes(db: Session, *, now: datetime | None = None) -> int:
    """Erase the readable digits of every customer code whose window has closed.

    forget_expired_display_codes needs an order; this is the whole-table pass a timer
    calls, so a code nobody ever came for stops being readable without anybody opening
    that order's page. The hash stays: it is what the door checks, and it is one-way.
    """
    now = now or datetime.now(timezone.utc)
    rows = list(db.scalars(
        select(LockerAccess).where(
            LockerAccess.kind == CUSTOMER,
            LockerAccess.display_code.is_not(None),
        )
    ))
    cleared = 0
    for access in rows:
        if _aware(access.valid_until) < now:
            access.display_code = None
            cleared += 1
    if cleared:
        db.flush()
    return cleared
