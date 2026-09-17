from __future__ import annotations

import hmac
import os

from fastapi import HTTPException, Request


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _same(provided: str, expected: str) -> bool:
    return bool(provided and expected) and hmac.compare_digest(provided, expected)


def _dev_bypass() -> bool:
    return _truthy(os.getenv("ALLOW_INSECURE_DEV"))


def require_operator(request: Request) -> str:
    if _dev_bypass():
        return "dev"
    operator_key = os.getenv("OPERATOR_API_KEY", "")
    admin_key = os.getenv("ADMIN_API_KEY", "")
    if not operator_key or not admin_key:
        raise HTTPException(503, "Operator authentication is not configured")
    provided = request.headers.get("x-api-key", "")
    if _same(provided, admin_key):
        return "admin"
    if _same(provided, operator_key):
        return "operator"
    raise HTTPException(401, "Invalid operator API key")


def require_admin(request: Request) -> str:
    if _dev_bypass():
        return "dev-admin"
    admin_key = os.getenv("ADMIN_API_KEY", "")
    if not admin_key:
        raise HTTPException(503, "Admin authentication is not configured")
    provided = request.headers.get("x-api-key", "")
    if _same(provided, admin_key):
        return "admin"
    raise HTTPException(401, "Invalid admin API key")
