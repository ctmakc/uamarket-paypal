"""In-process throttles for public write surfaces.

Two mechanisms live here:

* ``RateLimiter`` caps how many requests one key may make inside a window. It answers
  "is this caller talking too fast".
* ``FailureLockout`` counts *failed* attempts and holds the key shut for a cooldown once
  there have been too many. It answers "has this caller been guessing".

One process, one dict. Good enough for a single-container shop; swap for Redis when
there is more than one app replica. Never used for reads.
"""
from __future__ import annotations

import hmac
import os
import threading
import time
from collections import deque
from dataclasses import dataclass


class RateLimiter:
    def __init__(self, *, limit: int, window_seconds: float):
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, *, now: float | None = None, limit: int | None = None, window: float | None = None) -> bool:
        limit = self.limit if limit is None else limit
        window = self.window if window is None else window
        now = time.monotonic() if now is None else now
        with self._lock:
            q = self._hits.setdefault(key, deque())
            while q and now - q[0] > window:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True

    def would_block(self, key: str, *, now: float | None = None) -> bool:
        """True when the next `allow` for this key would refuse. Records nothing."""
        now = time.monotonic() if now is None else now
        with self._lock:
            q = self._hits.get(key)
            if not q:
                return False
            while q and now - q[0] > self.window:
                q.popleft()
            return len(q) >= self.limit

    def clear(self, key: str) -> bool:
        """Drop one key's history. Returns True if there was anything to drop."""
        with self._lock:
            return self._hits.pop(key, None) is not None

    def reset(self):
        with self._lock:
            self._hits.clear()


@dataclass(frozen=True)
class LockoutPolicy:
    """How many failures inside a window trip a lockout, and how long it lasts."""
    max_failures: int
    window_seconds: float
    lockout_seconds: float


class FailureLockout:
    """Counts failed attempts per key and locks that key out after too many of them.

    A locked key stays locked until its cooldown expires or an operator calls ``clear``.
    Nothing here is persisted: a process restart forgets the lockouts, which is the same
    trade-off ``RateLimiter`` already makes. The durable record of a lockout is the
    ExceptionRecord the caller writes.
    """

    def __init__(self):
        self._failures: dict[str, deque[float]] = {}
        self._locked_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def retry_after(self, key: str, *, now: float | None = None) -> float | None:
        """Seconds left on the lockout, or None when the key is free to try again."""
        now = time.monotonic() if now is None else now
        with self._lock:
            until = self._locked_until.get(key)
            if until is None:
                return None
            if until <= now:
                self._locked_until.pop(key, None)
                self._failures.pop(key, None)
                return None
            return until - now

    def is_locked(self, key: str, *, now: float | None = None) -> bool:
        return self.retry_after(key, now=now) is not None

    def failure_count(self, key: str, policy: LockoutPolicy, *, now: float | None = None) -> int:
        now = time.monotonic() if now is None else now
        with self._lock:
            q = self._failures.get(key)
            if not q:
                return 0
            return sum(1 for at in q if now - at <= policy.window_seconds)

    def register_failure(self, key: str, policy: LockoutPolicy, *, now: float | None = None) -> bool:
        """Record one failed attempt.

        Returns True only on the attempt that trips the lockout, so the caller can write
        exactly one ExceptionRecord per lockout instead of one per failure.
        """
        now = time.monotonic() if now is None else now
        with self._lock:
            locked_until = self._locked_until.get(key)
            if locked_until is not None and locked_until > now:
                return False
            q = self._failures.setdefault(key, deque())
            while q and now - q[0] > policy.window_seconds:
                q.popleft()
            q.append(now)
            if len(q) >= policy.max_failures:
                self._locked_until[key] = now + policy.lockout_seconds
                return True
            return False

    def clear(self, key: str) -> bool:
        """Operator recovery: forget this key's failures and lockout."""
        with self._lock:
            had = self._locked_until.pop(key, None) is not None
            had = (self._failures.pop(key, None) is not None) or had
            return had

    def reset(self):
        with self._lock:
            self._failures.clear()
            self._locked_until.clear()


# ------------------------------------------------------------------ who is calling
#
# Every guard in this file is keyed by the caller's address, so the address has to be read
# the same way everywhere. Two readings mean two keys for one caller, and a caller who can
# choose which key they land under is not guarded at all.
#
# In production nobody reaches this API directly except Caddy (for /webhooks/stripe) and the
# storefront's own server. Caddy writes the visitor's socket address into X-Real-IP; the
# storefront server passes it on as `X-Client-IP` together with `X-Internal-Proxy-Secret`:
#
#   INTERNAL_PROXY_SECRET  a long random value shared by Caddy, web and this API. The client
#                          address header is believed only when the request carries it.
#
# Without the secret (or with the wrong one) the header is ignored, so a visitor who writes
# X-Client-IP or X-Forwarded-For themselves lands under the address the socket shows.
#
#   TRUSTED_PROXY_IPS      advanced, for a deployment without the shared secret: proxy
#                          addresses whose `X-Forwarded-For` is believed. Empty by default.


def internal_proxy_secret() -> str:
    return (os.getenv("INTERNAL_PROXY_SECRET") or "").strip()


def trusted_proxies() -> frozenset[str]:
    """The proxy addresses whose `X-Forwarded-For` this API believes."""
    return frozenset(part.strip() for part in (os.getenv("TRUSTED_PROXY_IPS") or "").split(",") if part.strip())


def _internal_client(request) -> str | None:
    secret = internal_proxy_secret()
    if len(secret) < 16:
        return None
    supplied = request.headers.get("x-internal-proxy-secret") or ""
    if not supplied or not hmac.compare_digest(supplied, secret):
        return None
    ip = (request.headers.get("x-client-ip") or "").strip()
    return ip[:120] or None


def client_address(request) -> str:
    """One reading of the client address, shared by every guard on every public surface."""
    internal = _internal_client(request)
    if internal:
        return internal
    peer = request.client.host if getattr(request, "client", None) else ""
    peer = (peer or "unknown")[:120]
    trusted = trusted_proxies()
    if peer in trusted:
        chain = (request.headers.get("x-forwarded-for") or "").split(",")
        for hop in reversed(chain):
            hop = hop.strip()
            if hop and hop not in trusted:
                return hop[:120]
    return peer


def _int_env(name: str, default: int, *, minimum: int = 1) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= minimum else default


# 10 order attempts per IP per 10 minutes; status lookups 60 per 10 minutes. Requests the API
# refuses as invalid (a missing field, a bad postal code) count in their own bucket of 30, so
# a buyer correcting a form does not use up the attempts that place an order, and a script
# posting garbage is still cut off.
order_limiter = RateLimiter(limit=10, window_seconds=600)
order_invalid_limiter = RateLimiter(limit=30, window_seconds=600)
lookup_limiter = RateLimiter(limit=60, window_seconds=600)

# ------------------------------------------------------------------ courier PIN entry
#
# /courier/access/verify is public and opens a physical door, so it carries three
# guards. Every number below is a default that the operator can change with an
# environment variable (see docs/OWNER-ACTIONS.md); the code never assumes the shop
# agreed to these values.
#
#   COURIER_PIN_ATTEMPTS_PER_WINDOW   30   requests per address per window (traffic cap)
#   COURIER_PIN_ATTEMPT_WINDOW_SECONDS 600 length of that traffic window
#   COURIER_PIN_MAX_FAILURES           5   failed PINs for one pickup before lockout
#   COURIER_PIN_FAILURE_WINDOW_SECONDS 900 how long failures are remembered
#   COURIER_PIN_LOCKOUT_SECONDS        900 how long a locked pickup stays shut
#   COURIER_PIN_IP_MAX_FAILURES       15   failed PINs from one address before lockout
#   COURIER_PIN_IP_LOCKOUT_SECONDS    900  how long a locked address stays shut
#
# A 6-digit PIN is 1 000 000 combinations. At 5 tries per 15 minutes a single pickup
# window cannot be exhausted, and the operator sees the attempt as an exception.

COURIER_PIN_ATTEMPTS_PER_WINDOW = 30
COURIER_PIN_ATTEMPT_WINDOW_SECONDS = 600
COURIER_PIN_MAX_FAILURES = 5
COURIER_PIN_FAILURE_WINDOW_SECONDS = 900
COURIER_PIN_LOCKOUT_SECONDS = 900
COURIER_PIN_IP_MAX_FAILURES = 15
COURIER_PIN_IP_LOCKOUT_SECONDS = 900

courier_pin_limiter = RateLimiter(limit=COURIER_PIN_ATTEMPTS_PER_WINDOW, window_seconds=COURIER_PIN_ATTEMPT_WINDOW_SECONDS)
pickup_pin_lockout = FailureLockout()
courier_ip_lockout = FailureLockout()


def courier_attempt_limits() -> tuple[int, float]:
    """Traffic cap for PIN entry per client address: (requests, window seconds)."""
    return (
        _int_env("COURIER_PIN_ATTEMPTS_PER_WINDOW", COURIER_PIN_ATTEMPTS_PER_WINDOW),
        float(_int_env("COURIER_PIN_ATTEMPT_WINDOW_SECONDS", COURIER_PIN_ATTEMPT_WINDOW_SECONDS)),
    )


def courier_pin_policy() -> LockoutPolicy:
    """Lockout policy applied per pickup."""
    return LockoutPolicy(
        max_failures=_int_env("COURIER_PIN_MAX_FAILURES", COURIER_PIN_MAX_FAILURES),
        window_seconds=float(_int_env("COURIER_PIN_FAILURE_WINDOW_SECONDS", COURIER_PIN_FAILURE_WINDOW_SECONDS)),
        lockout_seconds=float(_int_env("COURIER_PIN_LOCKOUT_SECONDS", COURIER_PIN_LOCKOUT_SECONDS)),
    )


def courier_ip_policy() -> LockoutPolicy:
    """Lockout policy applied per client address, across all pickups."""
    return LockoutPolicy(
        max_failures=_int_env("COURIER_PIN_IP_MAX_FAILURES", COURIER_PIN_IP_MAX_FAILURES),
        window_seconds=float(_int_env("COURIER_PIN_FAILURE_WINDOW_SECONDS", COURIER_PIN_FAILURE_WINDOW_SECONDS)),
        lockout_seconds=float(_int_env("COURIER_PIN_IP_LOCKOUT_SECONDS", COURIER_PIN_IP_LOCKOUT_SECONDS)),
    )


def reset_courier_guards() -> None:
    """Clear every courier-PIN counter. Used by tests and by process-wide recovery."""
    courier_pin_limiter.reset()
    pickup_pin_lockout.reset()
    courier_ip_lockout.reset()
