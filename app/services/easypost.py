from __future__ import annotations

from typing import Any

import httpx


class EasyPostError(RuntimeError):
    pass


class EasyPostClient:
    BASE_URL = "https://api.easypost.com/v2"

    def __init__(self, api_key: str, *, transport: httpx.BaseTransport | None = None):
        if not api_key:
            raise EasyPostError("EASYPOST_API_KEY is not configured")
        self.api_key = api_key
        self.transport = transport

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict[str, Any]:
        try:
            with httpx.Client(
                base_url=self.BASE_URL,
                auth=(self.api_key, ""),
                timeout=20.0,
                transport=self.transport,
            ) as client:
                response = client.request(method, path, json=payload)
        except httpx.HTTPError as exc:
            raise EasyPostError(f"EasyPost transport error: {exc}") from exc
        if response.status_code >= 400:
            try:
                detail = response.json()
            except Exception:
                detail = response.text
            raise EasyPostError(f"EasyPost {response.status_code}: {detail}")
        return response.json()

    def create_shipment(self, *, to_address: dict, from_address: dict, parcel: dict, reference: str) -> dict:
        return self._request("POST", "/shipments", {"shipment": {
            "to_address": to_address,
            "from_address": from_address,
            "parcel": parcel,
            "reference": reference,
        }})

    def buy_shipment(self, shipment_id: str, rate_id: str) -> dict:
        return self._request("POST", f"/shipments/{shipment_id}/buy", {"rate": {"id": rate_id}})

    def create_pickup(
        self, *, address: dict, shipment_id: str, carrier_accounts: list[str],
        min_datetime: str, max_datetime: str, instructions: str, reference: str,
    ) -> dict:
        return self._request("POST", "/pickups", {"pickup": {
            "address": address,
            "shipment": {"id": shipment_id},
            "carrier_accounts": carrier_accounts,
            "min_datetime": min_datetime,
            "max_datetime": max_datetime,
            "instructions": instructions,
            "reference": reference,
        }})

    def buy_pickup(self, pickup_id: str, carrier: str, service: str) -> dict:
        return self._request("POST", f"/pickups/{pickup_id}/buy", {"carrier": carrier, "service": service})
