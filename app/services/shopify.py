from __future__ import annotations

import base64
import hashlib
import hmac
import json


class ShopifyWebhookError(RuntimeError):
    pass


def verify_hmac(raw_body: bytes, provided_hmac: str, client_secret: str) -> bool:
    if not provided_hmac or not client_secret:
        return False
    computed = base64.b64encode(
        hmac.new(client_secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
    ).decode("utf-8")
    return hmac.compare_digest(provided_hmac, computed)


def normalize_paid_order(raw_body: bytes, *, event_id: str, topic: str) -> dict:
    try:
        data = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise ShopifyWebhookError("Invalid JSON") from exc

    external_id = str(data.get("id") or data.get("admin_graphql_api_id") or "")
    if not external_id:
        raise ShopifyWebhookError("Shopify order has no id")

    lines = []
    for item in data.get("line_items", []):
        sku = (item.get("sku") or "").strip()
        if not sku:
            raise ShopifyWebhookError("Shopify line item missing SKU")
        try:
            unit_price = float(item.get("price") or 0)
        except (TypeError, ValueError) as exc:
            raise ShopifyWebhookError(f"Invalid price for SKU {sku}") from exc
        lines.append({"sku": sku, "qty": int(item.get("quantity") or 0), "unit_price_cad": unit_price})

    if not lines or any(x["qty"] <= 0 for x in lines):
        raise ShopifyWebhookError("Shopify order has no shippable line items")

    return {
        "source": "shopify",
        "event_id": event_id,
        "channel": "SHOPIFY",
        "external_order_id": external_id,
        "topic": topic,
        "lines": lines,
    }
