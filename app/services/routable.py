"""One rule for "is this an address mail can reach", used everywhere the API reads one.

A value such as `pay@uamarket.local` is a placeholder. Printing it as the place to send an
e-Transfer, or as the address a customer should write to, or using it as the sender of the
shop's email, tells a person something that cannot work. Every reader treats such a value
exactly as if the setting were empty.

Reserved names (RFC 2606, RFC 6761, RFC 6762): the top-level domains `.local`, `.localhost`,
`.test`, `.invalid`, `.example` and `.internal`, and the documentation domains `example.*`
at the second level (example.com, example.net, example.org, example.ca, ...).
"""
from __future__ import annotations

import re
from email.utils import parseaddr

NON_ROUTABLE_TLDS = frozenset({"local", "localhost", "test", "invalid", "example", "internal"})

_LOCAL_PART = re.compile(r"^[^@\s]+$")
_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", re.IGNORECASE)


def bare_address(value: str | None) -> str:
    """`UA Market <shop@x.ca>` and `shop@x.ca` both give `shop@x.ca`."""
    raw = (value or "").strip()
    if not raw:
        return ""
    return (parseaddr(raw)[1] or "").strip()


def is_routable_email(value: str | None) -> bool:
    address = bare_address(value)
    if address.count("@") != 1:
        return False
    local, domain = address.rsplit("@", 1)
    if not _LOCAL_PART.match(local):
        return False
    labels = domain.lower().rstrip(".").split(".")
    if len(labels) < 2 or not all(_LABEL.match(label) for label in labels):
        return False
    if labels[-1] in NON_ROUTABLE_TLDS:
        return False
    if labels[-2] == "example":
        return False
    return True


def routable_or_none(value: str | None) -> str | None:
    """The address as configured when mail can reach it, otherwise None."""
    raw = (value or "").strip()
    return raw if raw and is_routable_email(raw) else None
