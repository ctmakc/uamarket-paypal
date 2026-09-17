from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Device
from ..edge_models import EdgeCredential


@dataclass(frozen=True)
class EdgeIdentity:
    device_id: str
    site: str
    legacy_dev: bool = False


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def insecure_dev_enabled() -> bool:
    return _truthy(os.getenv("ALLOW_INSECURE_DEV"))


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def rotate_credential(db: Session, *, device_id: str, site: str = "default") -> tuple[EdgeCredential, str]:
    device = db.get(Device, device_id)
    if not device:
        device = Device(id=device_id, kind="EDGE", state="PROVISIONED")
        db.add(device)
        db.flush()
    token = secrets.token_urlsafe(40)
    digest = hash_token(token)
    credential = db.scalar(
        select(EdgeCredential).where(EdgeCredential.device_id == device_id, EdgeCredential.site == site)
    )
    now = datetime.now(timezone.utc)
    if credential:
        credential.token_hash = digest
        credential.enabled = True
        credential.rotated_at = now
    else:
        credential = EdgeCredential(
            device_id=device_id,
            site=site,
            token_hash=digest,
            enabled=True,
            created_at=now,
            rotated_at=now,
        )
        db.add(credential)
    db.flush()
    return credential, token


def revoke_credential(db: Session, *, device_id: str, site: str = "default") -> EdgeCredential | None:
    credential = db.scalar(
        select(EdgeCredential).where(EdgeCredential.device_id == device_id, EdgeCredential.site == site)
    )
    if credential:
        credential.enabled = False
        db.flush()
    return credential


def credential_recheck_seconds() -> float:
    """How often a live edge session re-checks its credential.

    Default 5 seconds (EDGE_CREDENTIAL_RECHECK_SECONDS). 0 means every loop.
    """
    try:
        return max(0.0, float(os.getenv("EDGE_CREDENTIAL_RECHECK_SECONDS", "5")))
    except ValueError:
        return 5.0


def credential_still_valid(db: Session, *, identity: EdgeIdentity, token: str | None) -> bool:
    """Read-only re-check of an already authenticated session.

    A WebSocket authenticates once and can then stay open for days. Revoking or
    rotating the token has to end that session as well, otherwise a credential
    an operator believes is dead keeps receiving UNLOCK commands. This does not
    touch last_used_at or device state, so it is cheap enough to run on the
    connection loop.
    """
    token = token or ""
    if identity.legacy_dev:
        if not insecure_dev_enabled():
            return False
        legacy = os.getenv("EDGE_SHARED_TOKEN", "dev-edge-token")
        return bool(token and legacy and hmac.compare_digest(token, legacy))
    if not token:
        return False
    credential = db.scalar(
        select(EdgeCredential).where(
            EdgeCredential.device_id == identity.device_id,
            EdgeCredential.site == identity.site,
            EdgeCredential.enabled.is_(True),
        )
    )
    if not credential:
        return False
    return hmac.compare_digest(hash_token(token), credential.token_hash)


def authenticate_edge(
    db: Session,
    *,
    device_id: str | None,
    site: str | None,
    token: str | None,
) -> EdgeIdentity | None:
    site = site or "default"
    token = token or ""
    if insecure_dev_enabled():
        legacy = os.getenv("EDGE_SHARED_TOKEN", "dev-edge-token")
        if token and legacy and hmac.compare_digest(token, legacy):
            return EdgeIdentity(
                device_id=device_id or os.getenv("EDGE_DEVICE_ID", "LOCKER-PLC-01"),
                site=site,
                legacy_dev=True,
            )
    if not device_id or not token:
        return None
    credential = db.scalar(
        select(EdgeCredential).where(
            EdgeCredential.device_id == device_id,
            EdgeCredential.site == site,
            EdgeCredential.enabled.is_(True),
        )
    )
    if not credential or not hmac.compare_digest(hash_token(token), credential.token_hash):
        return None
    credential.last_used_at = datetime.now(timezone.utc)
    device = db.get(Device, device_id)
    if device:
        device.last_seen_at = credential.last_used_at
        device.state = "ONLINE"
    db.flush()
    return EdgeIdentity(device_id=device_id, site=site)
